import streamDeck, { action, KeyDownEvent, SingletonAction } from "@elgato/streamdeck";
import { getBaseUrl } from "../config";

/** Opens the Webcam Tools web app in the default browser. */
@action({ UUID: "com.webcam-tools.streamdeck.openweb" })
export class OpenWebAction extends SingletonAction {
	override async onKeyDown(ev: KeyDownEvent): Promise<void> {
		const baseUrl = await getBaseUrl();
		await streamDeck.system.openUrl(baseUrl);
		await ev.action.showOk();
	}
}
