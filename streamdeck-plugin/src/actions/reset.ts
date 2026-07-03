import { action, KeyDownEvent, SingletonAction } from "@elgato/streamdeck";
import streamDeck from "@elgato/streamdeck";
import { apiPost } from "../config";

/** Resets both hardware exposure and post-processing controls to defaults in one press. */
@action({ UUID: "com.webcam-tools.streamdeck.reset" })
export class ResetAction extends SingletonAction {
	override async onKeyDown(ev: KeyDownEvent): Promise<void> {
		try {
			await apiPost("/api/camera/reset", {});
			await ev.action.showOk();
		} catch (err) {
			streamDeck.logger.error(`Reset failed: ${err}`);
			await ev.action.showAlert();
		}
	}
}
