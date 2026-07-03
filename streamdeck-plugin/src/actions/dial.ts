import { action, DialAction, DialDownEvent, DialRotateEvent, SingletonAction, WillAppearEvent } from "@elgato/streamdeck";
import { apiGet, apiPost } from "../config";

type ControlKey = "exposure" | "hw_brightness" | "brightness" | "contrast" | "saturation";

type DialSettings = {
	control?: ControlKey;
};

interface ControlDef {
	label: string;
	min: number;
	max: number;
	step: number;
	format: (v: number) => string;
}

const CONTROLS: Record<ControlKey, ControlDef> = {
	exposure: { label: "Exposure (HW)", min: -13, max: 0, step: 1, format: (v) => `${v}` },
	hw_brightness: { label: "Brightness (HW)", min: 0, max: 255, step: 5, format: (v) => `${v}` },
	brightness: { label: "Brightness", min: -100, max: 100, step: 5, format: (v) => `${v}` },
	contrast: { label: "Contrast", min: 50, max: 200, step: 5, format: (v) => `${v}%` },
	saturation: { label: "Saturation", min: 0, max: 200, step: 5, format: (v) => `${v}%` },
};

/**
 * Maps a Stream Deck+ dial to one of Webcam Tools's image controls. Configure
 * which control per-dial via its Property Inspector. Rotating the exposure
 * dial also flips auto-exposure off -- same convention real cameras use:
 * touching the manual control signals manual intent.
 *
 * Uses a custom touchscreen layout (layouts/dial.json: a label + a progress
 * bar) instead of the built-in $X1 layout, since $X1 only shows a title --
 * setFeedback lets us show the value as an actual bar, not just text.
 */
@action({ UUID: "com.webcam-tools.streamdeck.dial" })
export class DialControlAction extends SingletonAction<DialSettings> {
	// Local cache of last-known values, keyed by control, so relative dial
	// rotation has something to add/subtract from without a round-trip per tick.
	private cache = new Map<ControlKey, number>();

	override async onWillAppear(ev: WillAppearEvent<DialSettings>): Promise<void> {
		if (!ev.action.isDial()) return;
		const control = ev.payload.settings.control ?? "exposure";
		await this.syncAndShow(ev.action, control);
	}

	override async onDialRotate(ev: DialRotateEvent<DialSettings>): Promise<void> {
		const control = ev.payload.settings.control ?? "exposure";
		const def = CONTROLS[control];
		const current = this.cache.get(control) ?? (await this.fetchValue(control));
		const next = clamp(current + ev.payload.ticks * def.step, def.min, def.max);
		this.cache.set(control, next);

		try {
			await this.push(control, next);
			await this.showValue(ev.action, control, next);
		} catch {
			await ev.action.showAlert();
		}
	}

	override async onDialDown(ev: DialDownEvent<DialSettings>): Promise<void> {
		// Press resets to a sane default for the bound control.
		const control = ev.payload.settings.control ?? "exposure";
		const reset = DEFAULTS[control];
		this.cache.set(control, reset);
		try {
			await this.push(control, reset);
			await this.showValue(ev.action, control, reset);
		} catch {
			await ev.action.showAlert();
		}
	}

	private async syncAndShow(action: DialAction<DialSettings>, control: ControlKey): Promise<void> {
		try {
			const value = await this.fetchValue(control);
			this.cache.set(control, value);
			await this.showValue(action, control, value);
		} catch {
			await action.setFeedback({ label: `${CONTROLS[control].label}: --` });
		}
	}

	private async showValue(action: DialAction<DialSettings>, control: ControlKey, value: number): Promise<void> {
		const def = CONTROLS[control];
		await action.setFeedback({
			label: `${def.label}: ${def.format(value)}`,
			value_bar: { value, range: { min: def.min, max: def.max } },
		});
	}

	private async fetchValue(control: ControlKey): Promise<number> {
		if (control === "exposure" || control === "hw_brightness") {
			const hw = await apiGet<{ exposure: number; brightness: number }>("/api/camera/hardware");
			return control === "exposure" ? hw.exposure : hw.brightness;
		}
		const adj = await apiGet<{ brightness: number; contrast: number; saturation: number }>(
			"/api/camera/adjustments",
		);
		if (control === "brightness") return adj.brightness;
		if (control === "contrast") return Math.round(adj.contrast * 100);
		return Math.round(adj.saturation * 100);
	}

	private async push(control: ControlKey, value: number): Promise<void> {
		if (control === "exposure") {
			await apiPost("/api/camera/hardware", { auto_exposure: false, exposure: value });
		} else if (control === "hw_brightness") {
			await apiPost("/api/camera/hardware", { brightness: value });
		} else if (control === "brightness") {
			await apiPost("/api/camera/adjustments", { brightness: value });
		} else if (control === "contrast") {
			await apiPost("/api/camera/adjustments", { contrast: value / 100 });
		} else {
			await apiPost("/api/camera/adjustments", { saturation: value / 100 });
		}
	}
}

const DEFAULTS: Record<ControlKey, number> = {
	exposure: -6,
	hw_brightness: 128,
	brightness: 0,
	contrast: 100,
	saturation: 100,
};

function clamp(v: number, min: number, max: number): number {
	return Math.min(max, Math.max(min, v));
}
