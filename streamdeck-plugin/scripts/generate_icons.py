"""Generates action-list and key-face icons (flat white glyph on a
transparent background -- matches the icon pack adopted from the user's own
Stream Deck profile export, so hand-drawn ones don't look out of place next
to it) from simple PIL primitives. Only covers the actions that don't have an
adopted replacement (see the plugin README for how those were pulled out of
a .streamDeckProfile export). One-off tool, not part of the build pipeline --
re-run manually if you tweak a glyph:

    <webcam-tools backend venv python> scripts/generate_icons.py
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent / "com.webcam-tools.streamdeck.sdPlugin" / "imgs" / "actions"

WHITE = (255, 255, 255, 255)
RED = (255, 92, 92, 255)
GREEN = (110, 220, 140, 255)


def glyph_videocell(d, s):
    c = s / 2
    r = s * 0.34
    d.ellipse([c - r, c - r, c + r, c + r], outline=WHITE, width=max(2, int(s * 0.06)))
    rr = r * 0.42
    d.ellipse([c - rr, c - rr, c + rr, c + rr], fill=WHITE)
    dr = s * 0.09
    d.ellipse([s * 0.72 - dr, s * 0.14 - dr, s * 0.72 + dr, s * 0.14 + dr], fill=RED)


def glyph_livefeed(d, s):
    c = s / 2
    r = s * 0.32
    d.ellipse([c - r, c - r, c + r, c + r], outline=WHITE, width=max(2, int(s * 0.07)))


def glyph_dial(d, s):
    c = s / 2
    r = s * 0.34
    w = max(2, int(s * 0.07))
    d.ellipse([c - r, c - r, c + r, c + r], outline=WHITE, width=w)
    d.line([c, c - r + w, c, c - r * 0.35], fill=WHITE, width=w)


def glyph_stop(d, s):
    pad = s * 0.32
    d.rounded_rectangle([pad, pad, s - pad, s - pad], radius=s * 0.06, fill=WHITE)


def glyph_recordingstatus(d, s):
    c = s / 2
    r = s * 0.22
    d.ellipse([c - r, c - r, c + r, c + r], fill=RED)


def glyph_rotate(d, s):
    w = max(2, int(s * 0.07))
    d.rounded_rectangle([s * 0.3, s * 0.22, s * 0.7, s * 0.62], radius=s * 0.05, outline=WHITE, width=w)
    c = (s * 0.5, s * 0.72)
    r = s * 0.22
    d.arc([c[0] - r, c[1] - r, c[0] + r, c[1] + r], start=200, end=520, fill=WHITE, width=w)
    ang = math.radians(200)
    tip = (c[0] + r * math.cos(ang), c[1] + r * math.sin(ang))
    d.polygon(
        [
            (tip[0] - s * 0.02, tip[1] - s * 0.1),
            (tip[0] + s * 0.1, tip[1] - s * 0.06),
            (tip[0] + s * 0.02, tip[1] + s * 0.06),
        ],
        fill=WHITE,
    )


def glyph_openfolder(d, s):
    w = max(2, int(s * 0.07))
    d.line([s * 0.2, s * 0.32, s * 0.42, s * 0.32, s * 0.48, s * 0.4], fill=WHITE, width=w, joint="curve")
    d.polygon(
        [(s * 0.2, s * 0.4), (s * 0.78, s * 0.4), (s * 0.7, s * 0.72), (s * 0.14, s * 0.72)],
        outline=WHITE,
        width=w,
    )


def glyph_toggle_off(d, s):
    c = s / 2
    r = s * 0.28
    w = max(2, int(s * 0.08))
    d.arc([c - r, c - r, c + r, c + r], start=-235, end=55, fill=WHITE, width=w)
    d.line([c, s * 0.16, c, s * 0.5], fill=WHITE, width=w)


def glyph_toggle_on(d, s):
    # Manifest States are shared across every Pipeline Toggle instance --
    # can't be per-instance-icon-aware even when a key has its own custom
    # off-icon (e.g. a slashed bell/eye/camera from an adopted icon pack),
    # so this stays deliberately generic: a plain green "enabled" badge in
    # a similar thin-stroke line-art weight, meant to read fine next to any
    # icon it gets paired with rather than trying to match one specifically.
    c = s / 2
    r = s * 0.3
    w = max(2, int(s * 0.065))
    d.ellipse([c - r, c - r, c + r, c + r], outline=GREEN, width=w)
    d.line(
        [c - r * 0.45, c + r * 0.05, c - r * 0.12, c + r * 0.4, c + r * 0.5, c - r * 0.35],
        fill=GREEN,
        width=w,
        joint="curve",
    )


ACTIONS = {
    "videocell": glyph_videocell,
    "livefeed": glyph_livefeed,
    "dial": glyph_dial,
    "recordingstatus": glyph_recordingstatus,
    "rotate": glyph_rotate,
    "openfolder": glyph_openfolder,
    "pipelinetoggle": glyph_toggle_off,
}

# Launch declares two manifest States (0 = stopped/play, 1 = running/stop)
# and switches between them with action.setState() -- setImage() is a no-op
# once a user manually assigns a custom image, but per-state manifest images
# aren't subject to that restriction the same way.
STATE_ICONS = {
    ROOT / "launch": (glyph_stop, "stop"),
    ROOT / "pipelinetoggle": (glyph_toggle_on, "on"),
}


def make_icon(glyph, size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glyph(ImageDraw.Draw(img), size)
    return img


def main():
    for name, glyph in ACTIONS.items():
        out_dir = ROOT / name
        out_dir.mkdir(parents=True, exist_ok=True)

        make_icon(glyph, 20).save(out_dir / "icon.png")
        make_icon(glyph, 40).save(out_dir / "icon@2x.png")
        make_icon(glyph, 72).save(out_dir / "key.png")
        make_icon(glyph, 144).save(out_dir / "key@2x.png")
        print(f"generated {name}")

    for out_dir, (glyph, stem) in STATE_ICONS.items():
        out_dir.mkdir(parents=True, exist_ok=True)
        make_icon(glyph, 72).save(out_dir / f"{stem}.png")
        make_icon(glyph, 144).save(out_dir / f"{stem}@2x.png")
        print(f"generated {out_dir.name}/{stem}")


if __name__ == "__main__":
    main()
