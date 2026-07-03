import streamDeck from "@elgato/streamdeck";
import { spawn } from "node:child_process";
import { lookup } from "node:dns/promises";

export const DEFAULT_BASE_URL = "http://webcam-tools.local:8000";

// A solo mDNS (.local) lookup through Node's resolver on Windows measured
// ~2.7s here, but there's up to ~10 actions (Status, Recording Status,
// Launch, 4 dials, Video Cell, Live Feed) each polling independently -- with
// no caching, that's up to ~10 *concurrent* mDNS resolutions, and multicast
// resolution doesn't parallelize well, so individual lookups under that
// contention took longer than even a generous 5s timeout. A bigger timeout
// just chases a moving target; resolveIp() below caches the resolved
// address so only one real lookup happens per TTL window, and everything
// else reuses it -- eliminates the contention instead of tolerating it.
export const DEFAULT_TIMEOUT_MS = 5000;

const DNS_CACHE_MS = 60_000;
let dnsCache: { hostname: string; ip: string; at: number } | null = null;
let dnsInFlight: Promise<string> | null = null;

async function resolveIp(hostname: string): Promise<string> {
	const now = Date.now();
	if (dnsCache && dnsCache.hostname === hostname && now - dnsCache.at < DNS_CACHE_MS) {
		return dnsCache.ip;
	}
	if (dnsInFlight) return dnsInFlight;
	dnsInFlight = lookup(hostname)
		.then(({ address }) => {
			dnsCache = { hostname, ip: address, at: Date.now() };
			return address;
		})
		.finally(() => {
			dnsInFlight = null;
		});
	return dnsInFlight;
}

/** Rewrites a .local URL's hostname to its (cached) resolved IP; leaves anything else untouched. */
export async function resolveUrl(rawUrl: string): Promise<string> {
	const url = new URL(rawUrl);
	if (!url.hostname.endsWith(".local")) return rawUrl;
	try {
		url.hostname = await resolveIp(url.hostname);
		return url.toString();
	} catch {
		return rawUrl; // let fetch's own resolution (and our timeout) handle a genuine failure
	}
}

type GlobalSettings = {
	baseUrl?: string;
	scriptPath?: string;
};

/**
 * All actions share one base URL (and one launch-script path) via Stream
 * Deck's global settings, so you only configure it once instead of once
 * per button.
 */
export async function getBaseUrl(): Promise<string> {
	const settings = await streamDeck.settings.getGlobalSettings<GlobalSettings>();
	return settings.baseUrl?.trim() || DEFAULT_BASE_URL;
}

export async function getScriptPath(): Promise<string | undefined> {
	const settings = await streamDeck.settings.getGlobalSettings<GlobalSettings>();
	return settings.scriptPath?.trim() || undefined;
}

// Every action swallows fetch failures into a quiet "Offline"/alert state by
// design (a poll failing once a second shouldn't spam), but that means a
// real misconfiguration (wrong baseUrl, DNS/mDNS issue, server actually
// down) was previously invisible anywhere. Log once per distinct failure
// (and once on recovery) so `streamdeck-plugin/.../logs/*.log` actually
// shows what's wrong instead of just "it's offline."
let lastLoggedFailure: string | null = null;

function logOutcome(url: string, error: unknown | null): void {
	if (error) {
		const msg = `${url} -- ${error instanceof Error ? error.message : String(error)}`;
		if (msg !== lastLoggedFailure) {
			streamDeck.logger.warn(`Request failed: ${msg}`);
			lastLoggedFailure = msg;
		}
	} else if (lastLoggedFailure) {
		streamDeck.logger.info(`Requests to ${new URL(url).origin} are reachable again.`);
		lastLoggedFailure = null;
	}
}

/**
 * Fetches JSON from the Webcam Tools API with a short timeout -- Stream Deck
 * buttons should fail fast (show an alert) rather than hang if the server
 * is offline.
 */
export async function apiGet<T = unknown>(path: string, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<T> {
	const baseUrl = await getBaseUrl();
	const rawUrl = `${baseUrl}${path}`;
	const url = await resolveUrl(rawUrl);
	const controller = new AbortController();
	const timer = setTimeout(() => controller.abort(), timeoutMs);
	try {
		const res = await fetch(url, { signal: controller.signal });
		if (!res.ok) throw new Error(`${path} -> ${res.status}`);
		const json = (await res.json()) as T;
		logOutcome(rawUrl, null);
		return json;
	} catch (err) {
		logOutcome(rawUrl, err);
		throw err;
	} finally {
		clearTimeout(timer);
	}
}

export async function apiPost<T = unknown>(path: string, body: unknown, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<T> {
	const baseUrl = await getBaseUrl();
	const rawUrl = `${baseUrl}${path}`;
	const url = await resolveUrl(rawUrl);
	const controller = new AbortController();
	const timer = setTimeout(() => controller.abort(), timeoutMs);
	try {
		const res = await fetch(url, {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify(body),
			signal: controller.signal,
		});
		if (!res.ok) throw new Error(`${path} -> ${res.status}`);
		const json = (await res.json()) as T;
		logOutcome(rawUrl, null);
		return json;
	} catch (err) {
		logOutcome(rawUrl, err);
		throw err;
	} finally {
		clearTimeout(timer);
	}
}

export interface WebcamToolsStatus {
	connected: boolean;
	paused: boolean;
	recording: boolean;
	recording_event_type: string | null;
	shutting_down: boolean;
	camera_index: number;
	camera_name: string | null;
	fps: number;
}

/**
 * The server (and start.bat) only exist on the Windows host. On a Mac (or
 * any other client) Stream Deck instance, everything that's a plain HTTP
 * call or Stream Deck's own openUrl still works over the LAN -- only
 * spawning start.bat is Windows-only.
 */
export function canLaunch(): boolean {
	return process.platform === "win32";
}

export async function isServerUp(timeoutMs = DEFAULT_TIMEOUT_MS): Promise<boolean> {
	try {
		await apiGet<WebcamToolsStatus>("/api/status", timeoutMs);
		return true;
	} catch {
		return false;
	}
}

/** Polls until the server responds or the timeout elapses. Returns whether it came up. */
export async function waitForServer(timeoutMs = 20000, intervalMs = 750): Promise<boolean> {
	const deadline = Date.now() + timeoutMs;
	while (Date.now() < deadline) {
		if (await isServerUp()) return true;
		await new Promise((r) => setTimeout(r, intervalMs));
	}
	return false;
}

/**
 * Spawns start.bat (Windows only -- callers should check canLaunch() first).
 * Detached with its own console window so the server keeps running, and its
 * logs stay visible, independent of the Stream Deck app's lifecycle.
 */
export async function launchServer(): Promise<boolean> {
	const scriptPath = await getScriptPath();
	if (!scriptPath) {
		streamDeck.logger.error("No start.bat path configured (set it in any Webcam Tools action's Property Inspector).");
		return false;
	}
	try {
		const child = spawn("cmd.exe", ["/c", "start", "Webcam Tools", scriptPath], {
			detached: true,
			stdio: "ignore",
			windowsHide: false,
		});
		child.unref();
		return true;
	} catch (err) {
		streamDeck.logger.error(`Failed to launch start.bat: ${err}`);
		return false;
	}
}
