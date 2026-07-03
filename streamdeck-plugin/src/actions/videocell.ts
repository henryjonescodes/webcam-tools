import { action, KeyDownEvent, KeyUpEvent, SingletonAction, WillAppearEvent, WillDisappearEvent } from "@elgato/streamdeck";
import streamDeck from "@elgato/streamdeck";
import { canLaunch, DEFAULT_TIMEOUT_MS, getBaseUrl, isServerUp, launchServer, resolveUrl, waitForServer } from "../config";

const POLL_MS = 1000;
const LONG_PRESS_MS = 450;

// Must be *identical* to manifest.json's Profiles[].Name (the SDK docs are
// explicit about this) -- that's declared as "profiles/webcam-tools", not
// just "webcam-tools", so this has to match including the folder prefix.
const PROFILE_NAME = "profiles/webcam-tools";

/**
 * The single entry point onto the whole plugin: shows a live-updating
 * thumbnail (like the standalone Live Feed action) AND doubles as
 * navigation, so you only spend one button on your main profile instead of
 * two (a feed tile + a separate "open panel" button).
 *
 * - Short press: switches this Stream Deck to the bundled Webcam Tools
 *   profile (dials + status + open-web-app).
 * - Long press: "smart open" -- opens the web app, launching the Windows
 *   host first if it's not already reachable (Windows only; on a Mac or
 *   other client there's nothing to launch, so it just opens the app if
 *   already reachable).
 */
@action({ UUID: "com.webcam-tools.streamdeck.videocell" })
export class VideoCellAction extends SingletonAction {
	private pollTimer: ReturnType<typeof setInterval> | undefined;
	private pressStartedAt = new Map<string, number>();
	private offline = false;
	private inFlight = false;

	override onWillAppear(_ev: WillAppearEvent): void {
		if (this.pollTimer) return;
		this.pollTimer = setInterval(() => void this.refreshImage(), POLL_MS);
		void this.refreshImage();
	}

	override onWillDisappear(_ev: WillDisappearEvent): void {
		if ([...this.actions].length > 0) return;
		if (this.pollTimer) {
			clearInterval(this.pollTimer);
			this.pollTimer = undefined;
		}
	}

	override onKeyDown(ev: KeyDownEvent): void {
		this.pressStartedAt.set(ev.action.id, Date.now());
	}

	override async onKeyUp(ev: KeyUpEvent): Promise<void> {
		const startedAt = this.pressStartedAt.get(ev.action.id);
		this.pressStartedAt.delete(ev.action.id);
		const held = startedAt ? Date.now() - startedAt : 0;

		if (held >= LONG_PRESS_MS) {
			await this.smartOpen(ev);
		} else {
			await this.openPanel(ev);
		}
	}

	private async openPanel(ev: KeyUpEvent): Promise<void> {
		try {
			await streamDeck.profiles.switchToProfile(ev.action.device.id, PROFILE_NAME);
		} catch (err) {
			streamDeck.logger.error(`Couldn't switch to the "${PROFILE_NAME}" profile: ${err}`);
			await ev.action.setTitle("No profile");
			await ev.action.showAlert();
		}
	}

	private async smartOpen(ev: KeyUpEvent): Promise<void> {
		if (await isServerUp()) {
			await streamDeck.system.openUrl(await getBaseUrl());
			await ev.action.showOk();
			return;
		}

		if (!canLaunch()) {
			// Viewing from a Mac (or similar): nothing we can start remotely.
			await ev.action.showAlert();
			return;
		}

		if (!(await launchServer())) {
			await ev.action.showAlert();
			return;
		}

		// A cold start just needs to come up -- it doesn't also need a
		// browser tab popped open on it (that tab, left open on the live
		// MJPEG stream, is exactly the kind of thing that can later hang a
		// graceful shutdown). Press again once it's up to actually open it.
		await waitForServer();
		await ev.action.showOk();
	}

	private async refreshImage(): Promise<void> {
		if (this.inFlight) return;
		this.inFlight = true;
		const baseUrl = await getBaseUrl();
		try {
			const url = await resolveUrl(`${baseUrl}/api/snapshot`);
			const res = await fetch(url, { signal: AbortSignal.timeout(DEFAULT_TIMEOUT_MS) });
			if (!res.ok) throw new Error(`snapshot -> ${res.status}`);
			const buf = Buffer.from(await res.arrayBuffer());
			const dataUri = `data:image/jpeg;base64,${buf.toString("base64")}`;
			for (const a of this.actions) {
				await a.setImage(dataUri);
			}
			if (this.offline) {
				this.offline = false;
				for (const a of this.actions) await a.setTitle("");
			}
		} catch {
			// A stale frozen frame reads as "live" at a glance -- fall back to
			// the plain default icon plus an explicit label so offline is
			// unmistakable, instead of quietly leaving the last good frame up.
			if (this.offline) return;
			this.offline = true;
			for (const a of this.actions) {
				await a.setImage();
				await a.setTitle("Offline");
			}
		} finally {
			this.inFlight = false;
		}
	}
}
