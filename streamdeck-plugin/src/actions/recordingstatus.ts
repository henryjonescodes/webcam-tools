import { action, KeyDownEvent, SingletonAction, WillAppearEvent, WillDisappearEvent } from "@elgato/streamdeck";
import { apiGet, DEFAULT_TIMEOUT_MS, WebcamToolsStatus } from "../config";

const POLL_MS = 5000;

function label(type: string | null): string {
	if (!type) return "REC";
	return `REC\n${type.charAt(0).toUpperCase()}${type.slice(1)}`;
}

/**
 * Separate from the general Status cell -- this one is only about whether
 * (and why) a clip is being recorded right now, e.g. "REC / Motion" vs
 * "REC / Manual", so the two don't have to fight over one line of text.
 */
@action({ UUID: "com.webcam-tools.streamdeck.recordingstatus" })
export class RecordingStatusAction extends SingletonAction {
	private timer: ReturnType<typeof setInterval> | undefined;

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

	override async onKeyDown(_ev: KeyDownEvent): Promise<void> {
		await this.poll();
	}

	private async poll(): Promise<void> {
		let status: WebcamToolsStatus | null = null;
		try {
			status = await apiGet<WebcamToolsStatus>("/api/status", DEFAULT_TIMEOUT_MS);
		} catch {
			status = null;
		}

		for (const a of this.actions) {
			if (!status) {
				await a.setTitle("Offline");
			} else if (status.shutting_down) {
				await a.setTitle("Stopping…");
			} else if (status.recording) {
				await a.setTitle(label(status.recording_event_type));
			} else {
				await a.setTitle("Idle");
			}
		}
	}
}
