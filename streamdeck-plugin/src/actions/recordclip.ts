import { action, KeyDownEvent, SingletonAction } from "@elgato/streamdeck";
import streamDeck from "@elgato/streamdeck";
import { apiPost } from "../config";

/** Manually records a clip right now, independent of motion detection. */
@action({ UUID: "com.webcam-tools.streamdeck.recordclip" })
export class RecordClipButtonAction extends SingletonAction {
	override async onKeyDown(ev: KeyDownEvent): Promise<void> {
		try {
			await apiPost("/api/events/record", {});
			await ev.action.showOk();
		} catch (err) {
			streamDeck.logger.error(`Manual record failed: ${err}`);
			await ev.action.showAlert();
		}
	}
}
