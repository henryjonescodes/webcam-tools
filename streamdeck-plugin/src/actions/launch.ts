import { action, KeyDownEvent, KeyUpEvent, SingletonAction, WillAppearEvent, WillDisappearEvent } from "@elgato/streamdeck";
import { apiGet, apiPost, canLaunch, launchServer, WebcamToolsStatus } from "../config";

const POLL_MS = 5000;
const LONG_PRESS_MS = 450;

/**
 * The one "power" button: short-press starts the server if it's stopped.
 * Once it's running the icon flips to a stop glyph, and *that* state's
 * short-press is a no-op -- you have to hold it (like Shutdown used to
 * require) to actually take the camera down, so a stray tap can't kill it.
 *
 * Uses the manifest's two declared States (0 = stopped/play, 1 =
 * running/stop) plus setState() rather than setImage() -- setImage() is a
 * no-op once a user manually assigns a custom image to a key, but a
 * different state's manifest image isn't subject to that restriction, so
 * this keeps working even on a key you've customized in the Stream Deck app.
 */
@action({ UUID: "com.webcam-tools.streamdeck.launch" })
export class LaunchAction extends SingletonAction {
	private timer: ReturnType<typeof setInterval> | undefined;
	private pressStartedAt = new Map<string, number>();
	private running = false;

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

	override onKeyDown(ev: KeyDownEvent): void {
		this.pressStartedAt.set(ev.action.id, Date.now());
	}

	override async onKeyUp(ev: KeyUpEvent): Promise<void> {
		const startedAt = this.pressStartedAt.get(ev.action.id);
		this.pressStartedAt.delete(ev.action.id);
		const held = startedAt ? Date.now() - startedAt : 0;

		if (held >= LONG_PRESS_MS) {
			// Always attempt this, even if our cached state thinks it's
			// stopped -- e.g. right after Stream Deck boots, before the
			// first poll lands, or an errant process is still holding the
			// camera without us knowing it. A hold should be a reliable
			// "make sure it's off" regardless of what we last saw.
			try {
				await apiPost("/api/system/shutdown", {});
				await ev.action.showOk();
				for (const a of this.actions) if (a.isKey()) await a.setTitle("Stopping…");
			} catch {
				// Most likely nothing was running to shut down -- not worth alarming over.
			}
			void this.poll();
			return;
		}

		if (this.running) {
			await ev.action.showOk();
			return;
		}

		if (!canLaunch()) {
			await ev.action.showAlert();
			return;
		}
		if (await launchServer()) {
			await ev.action.showOk();
			for (const a of this.actions) if (a.isKey()) await a.setTitle("Starting…");
		} else {
			await ev.action.showAlert();
		}
		void this.poll();
	}

	private async poll(): Promise<void> {
		let status: WebcamToolsStatus | null = null;
		try {
			status = await apiGet<WebcamToolsStatus>("/api/status");
		} catch {
			status = null;
		}

		// The server is still technically reachable during its shutdown grace
		// window, so the icon stays on "running" (with a "Stopping…" label)
		// until it's actually gone, rather than flipping to "stopped" early.
		this.running = status !== null;
		for (const a of this.actions) {
			if (!a.isKey()) continue;
			await a.setState(this.running ? 1 : 0);
			await a.setTitle(status?.shutting_down ? "Stopping…" : "");
		}
	}
}
