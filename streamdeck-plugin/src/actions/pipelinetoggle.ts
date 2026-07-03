import {
	action,
	KeyDownEvent,
	PropertyInspectorDidAppearEvent,
	SingletonAction,
	WillAppearEvent,
	WillDisappearEvent,
} from "@elgato/streamdeck";
import streamDeck from "@elgato/streamdeck";
import { apiGet, apiPost } from "../config";

const POLL_MS = 5000;

type Settings = { target?: string };

interface ToggleEntry {
	name: string;
	enabled: boolean;
}

interface Toggles {
	detectors: ToggleEntry[];
	actions: ToggleEntry[];
	image: ToggleEntry[];
}

type Category = keyof Toggles;
const CATEGORIES: Category[] = ["detectors", "actions", "image"];

function parseTarget(target: string | undefined): { category: Category; name: string } | null {
	if (!target) return null;
	const i = target.indexOf(":");
	if (i < 0) return null;
	const category = target.slice(0, i) as Category;
	const name = target.slice(i + 1);
	if (!CATEGORIES.includes(category) || !name) return null;
	return { category, name };
}

/**
 * One configurable button for *any* on/off pipeline stage -- a detector, an
 * action, or an image-processing toggle like anti-glare -- picked per-key
 * via the Property Inspector's dropdown, which is populated dynamically
 * from /api/toggles rather than a hardcoded list, so a new detector/action/
 * image toggle added later shows up here automatically without a plugin
 * update. Icon flips (manifest States 0/1, same setState() pattern as
 * Launch) and the title carries the specific name + on/off readout, since
 * the icon itself has to stay generic across whatever this is bound to.
 */
@action({ UUID: "com.webcam-tools.streamdeck.pipelinetoggle" })
export class PipelineToggleAction extends SingletonAction<Settings> {
	private timer: ReturnType<typeof setInterval> | undefined;

	override onWillAppear(_ev: WillAppearEvent<Settings>): void {
		if (this.timer) return;
		this.timer = setInterval(() => void this.pollAll(), POLL_MS);
		void this.pollAll();
	}

	override onWillDisappear(_ev: WillDisappearEvent<Settings>): void {
		if ([...this.actions].length > 0) return;
		if (this.timer) {
			clearInterval(this.timer);
			this.timer = undefined;
		}
	}

	override async onPropertyInspectorDidAppear(_ev: PropertyInspectorDidAppearEvent<Settings>): Promise<void> {
		let toggles: Toggles | null = null;
		try {
			toggles = await apiGet<Toggles>("/api/toggles");
		} catch {
			toggles = null;
		}
		const flat = toggles
			? CATEGORIES.flatMap((category) => toggles![category].map((t) => ({ category, name: t.name })))
			: [];
		await streamDeck.ui.sendToPropertyInspector({ toggles: flat });
	}

	override async onKeyDown(ev: KeyDownEvent<Settings>): Promise<void> {
		const parsed = parseTarget(ev.payload.settings.target);
		if (!parsed) {
			await ev.action.showAlert();
			return;
		}
		try {
			let toggles = await apiGet<Toggles>("/api/toggles");
			const entry = toggles[parsed.category].find((t) => t.name === parsed.name);
			if (!entry) {
				await ev.action.showAlert();
				return;
			}
			await apiPost(`/api/toggles/${parsed.category}/${parsed.name}/toggle`, { enabled: !entry.enabled });
			await ev.action.showOk();
			toggles = await apiGet<Toggles>("/api/toggles");
			await this.render(ev.action, parsed, toggles);
		} catch (err) {
			streamDeck.logger.error(`Pipeline toggle failed: ${err}`);
			await ev.action.showAlert();
		}
	}

	private async pollAll(): Promise<void> {
		let toggles: Toggles | null = null;
		try {
			toggles = await apiGet<Toggles>("/api/toggles");
		} catch {
			toggles = null;
		}

		for (const a of this.actions) {
			if (!a.isKey()) continue;
			const settings = await a.getSettings();
			const parsed = parseTarget(settings.target);
			await this.render(a, parsed, toggles);
		}
	}

	private async render(
		a: { isKey(): boolean; setState(s: 0 | 1): Promise<void>; setTitle(t: string): Promise<void> },
		parsed: { category: Category; name: string } | null,
		toggles: Toggles | null
	): Promise<void> {
		if (!parsed) {
			await a.setTitle("Not set");
			return;
		}
		if (!toggles) {
			await a.setTitle("Offline");
			return;
		}
		const entry = toggles[parsed.category].find((t) => t.name === parsed.name);
		if (!entry) {
			await a.setTitle("Not found");
			return;
		}
		await a.setState(entry.enabled ? 1 : 0);
		await a.setTitle(`${entry.name.replace(/_/g, " ")}\n${entry.enabled ? "On" : "Off"}`);
	}
}
