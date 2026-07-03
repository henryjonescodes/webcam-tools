#!/usr/bin/env node
// Swaps in a freshly-exported .streamDeckProfile and rebuilds/repacks the
// plugin so it's live. Usage:
//   npm run update-profile                       (auto-finds a dropped-in file)
//   npm run update-profile -- "C:\path\to\x.streamDeckProfile"

import { existsSync, copyFileSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { execSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const SCRIPTS_DIR = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(SCRIPTS_DIR, "..");
const PROJECT_ROOT = path.resolve(ROOT, "..");
const PLUGIN_DIR = path.join(ROOT, "com.webcam-tools.streamdeck.sdPlugin");
const PROFILE_NAME = "webcam-tools";
const DEST = path.join(PLUGIN_DIR, "profiles", `${PROFILE_NAME}.streamDeckProfile`);
const MANIFEST_PATH = path.join(PLUGIN_DIR, "manifest.json");

function findDroppedProfile() {
	// Looks in the plugin root and the parent (repo) root for any
	// .streamDeckProfile file -- wherever you happen to drop a fresh export.
	for (const dir of [ROOT, PROJECT_ROOT]) {
		const hit = readdirSync(dir).find((f) => f.toLowerCase().endsWith(".streamdeckprofile"));
		if (hit) return path.join(dir, hit);
	}
	return undefined;
}

const source = process.argv[2] || findDroppedProfile();

if (!source || !existsSync(source)) {
	console.error(
		"Couldn't find a .streamDeckProfile to use.\n" +
			"Export one from the Stream Deck app (right-click the profile -> Export),\n" +
			"then either drop it in this folder or the repo root and re-run,\n" +
			'or pass the path directly: npm run update-profile -- "C:\\path\\to\\file.streamDeckProfile"',
	);
	process.exit(1);
}

mkdirSync(path.dirname(DEST), { recursive: true });
copyFileSync(source, DEST);
console.log(`Copied:\n  ${source}\n  -> ${DEST}`);

// The manifest's "Profiles" entry is what makes Stream Deck offer to
// install this profile alongside the plugin -- there isn't one by default
// (no profile ships until you've actually exported your own layout), so
// add it the first time a profile shows up here.
const manifest = JSON.parse(readFileSync(MANIFEST_PATH, "utf-8"));
if (!manifest.Profiles) {
	manifest.Profiles = [
		{
			Name: `profiles/${PROFILE_NAME}`,
			DeviceType: 7, // Stream Deck+
			Readonly: false,
			DontAutoSwitchWhenInstalled: true,
		},
	];
	writeFileSync(MANIFEST_PATH, JSON.stringify(manifest, null, "\t") + "\n");
	console.log("Added a \"Profiles\" entry to manifest.json so this gets bundled with the plugin.");
}

console.log("\nRebuilding...");
execSync("npm run build", { cwd: ROOT, stdio: "inherit" });

console.log("\nPacking...");
execSync(`npx streamdeck pack ${path.basename(PLUGIN_DIR)} --force`, { cwd: ROOT, stdio: "inherit" });

console.log(
	`\nDone. Reinstall com.webcam-tools.streamdeck.streamDeckPlugin to pick up the new profile\n` +
		"(or `npx streamdeck restart com.webcam-tools.streamdeck` if dev-linked).",
);
