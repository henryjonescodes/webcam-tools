import { action, KeyDownEvent, SingletonAction, WillAppearEvent, WillDisappearEvent } from "@elgato/streamdeck";
import streamDeck from "@elgato/streamdeck";
import { apiGet, apiPost } from "../config";

const POLL_MS = 5000;

type RotationValue = 0 | 90 | 180 | 270;

const NEXT: Record<RotationValue, RotationValue> = { 0: 90, 90: 180, 180: 270, 270: 0 };

/**
 * Cycles the camera's mount-orientation rotation (0 -> 90 -> 180 -> 270 ->
 * 0) each press, same setting as the web app's Rotation control -- polls so
 * it stays in sync if it's changed from there instead.
 */
@action({ UUID: "com.webcam-tools.streamdeck.rotate" })
export class RotateAction extends SingletonAction {
	private timer: ReturnType<typeof setInterval> | undefined;
	private current: RotationValue | null = null;

	override onWillAppear(_ev: WillAppearEvent): void {
		if (this.timer) return;
		this.timer = setInterval(() => void this.poll(), POLL_MS);
		void this.poll();
	}

	override onWillDisappear(_ev: WillDisappearEvent): void {
		if ([...this.actions].length > 0) return;
		if (this.timer) {
			clearInterval(this.timer);
			this.timer = undefined;
		}
	}

	override async onKeyDown(ev: KeyDownEvent): Promise<void> {
		const from = this.current ?? 0;
		const next = NEXT[from];
		try {
			const result = await apiPost<{ rotation: RotationValue }>("/api/camera/rotation", { rotation: next });
			await this.show(result.rotation);
			await ev.action.showOk();
		} catch (err) {
			streamDeck.logger.error(`Rotate failed: ${err}`);
			await ev.action.showAlert();
		}
	}

	private async poll(): Promise<void> {
		try {
			const result = await apiGet<{ rotation: RotationValue }>("/api/camera/rotation");
			await this.show(result.rotation);
		} catch {
			// Leave the last known value showing -- Status already covers "offline".
		}
	}

	private async show(rotation: RotationValue): Promise<void> {
		this.current = rotation;
		for (const a of this.actions) await a.setTitle(`${rotation}°`);
	}
}
