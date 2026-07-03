import { action, KeyDownEvent, SingletonAction } from "@elgato/streamdeck";
import streamDeck from "@elgato/streamdeck";
import { apiPost } from "../config";

/** Opens the recordings folder in Explorer on the Webcam Tools host machine
 * (the server does the actual opening, so this works from any client --
 * Mac or Windows -- as long as the host itself is Windows). */
@action({ UUID: "com.webcam-tools.streamdeck.openfolder" })
export class OpenFolderAction extends SingletonAction {
	override async onKeyDown(ev: KeyDownEvent): Promise<void> {
		try {
			await apiPost("/api/system/open-recordings-folder", {});
			await ev.action.showOk();
		} catch (err) {
			streamDeck.logger.error(`Open recordings folder failed: ${err}`);
			await ev.action.showAlert();
		}
	}
}
