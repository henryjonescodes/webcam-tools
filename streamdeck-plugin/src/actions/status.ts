import { action, KeyDownEvent, SingletonAction, WillAppearEvent, WillDisappearEvent } from "@elgato/streamdeck";
import { apiGet, DEFAULT_TIMEOUT_MS, WebcamToolsStatus } from "../config";

const POLL_MS = 5000;

/**
 * Shows connection/recording state on the button. Polls only while at least
 * one instance of this action is visible on a Stream Deck, one shared timer
 * updates every visible instance.
 */
@action({ UUID: "com.webcam-tools.streamdeck.status" })
export class StatusAction extends SingletonAction {
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
			} else if (status.paused) {
				await a.setTitle("Paused");
			} else if (status.connected) {
				await a.setTitle(`Live\n${status.fps.toFixed(0)} fps`);
			} else {
				await a.setTitle("No camera");
			}
		}
	}
}
