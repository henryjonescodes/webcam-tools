import { action, KeyDownEvent, SingletonAction, WillAppearEvent, WillDisappearEvent } from "@elgato/streamdeck";
import { DEFAULT_TIMEOUT_MS, getBaseUrl, resolveUrl } from "../config";

// Stream Deck keys are tiny and setImage isn't meant for real video -- this
// polls a JPEG snapshot at a conservative rate so it doesn't hammer the
// Stream Deck app with image updates. Feels like a "live-ish" thumbnail
// rather than actual motion video.
const POLL_MS = 1000;

@action({ UUID: "com.webcam-tools.streamdeck.livefeed" })
export class LiveFeedAction extends SingletonAction {
	private timer: ReturnType<typeof setInterval> | undefined;
	private offline = false;
	private inFlight = false;

	override onWillAppear(_ev: WillAppearEvent): void {
		if (this.timer) return;
		this.timer = setInterval(() => void this.refresh(), POLL_MS);
		void this.refresh();
	}

	override onWillDisappear(_ev: WillDisappearEvent): void {
		if ([...this.actions].length > 0) return;
		if (this.timer) {
			clearInterval(this.timer);
			this.timer = undefined;
		}
	}

	override async onKeyDown(_ev: KeyDownEvent): Promise<void> {
		await this.refresh();
	}

	private async refresh(): Promise<void> {
		// A single request can legitimately take longer than the 1s poll
		// interval (mDNS resolution alone can take ~2-3s) -- without this,
		// slow polls pile up as concurrent in-flight requests instead of
		// just running back-to-back.
		if (this.inFlight) return;
		this.inFlight = true;
		const baseUrl = await getBaseUrl();
		try {
			const url = await resolveUrl(`${baseUrl}/api/snapshot`);
			const res = await fetch(url, { signal: AbortSignal.timeout(DEFAULT_TIMEOUT_MS) });
			if (!res.ok) throw new Error(`snapshot -> ${res.status}`);
			const buf = Buffer.from(await res.arrayBuffer());
			const dataUri = `data:image/jpeg;base64,${buf.toString("base64")}`;
			for (const a of this.actions) {
				await a.setImage(dataUri);
			}
			if (this.offline) {
				this.offline = false;
				for (const a of this.actions) await a.setTitle("");
			}
		} catch {
			// A stale frozen frame reads as "live" at a glance -- fall back to
			// the plain default icon plus an explicit label so offline is
			// unmistakable, instead of quietly leaving the last good frame up.
			if (this.offline) return;
			this.offline = true;
			for (const a of this.actions) {
				await a.setImage();
				await a.setTitle("Offline");
			}
		} finally {
			this.inFlight = false;
		}
	}
}
