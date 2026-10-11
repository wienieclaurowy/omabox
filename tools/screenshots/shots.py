"""Screenshots of the Omabox panel with invented data, in a second, sandboxed Quickshell.

    python3 tools/screenshots/shots.py OUT-DIR SCENARIO:THEME [SCENARIO:THEME...]

SCENARIO is feed, notifications, sources, reader, welcome, add or xtoken; THEME is an Omarchy theme folder name
(tokyo-night, catppuccin-latte, ...). Each shot shows a click-through overlay on one monitor (SHOTS_SCREEN, default
the focused one) for about five seconds. The live shell, its theme and the real Omabox data are not touched: the rig
runs on a copy of the shell's Commons and Ui, a sandbox home from demo.py and its own runtime directory.
Needs qs, grim, hyprctl and python3-pillow.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parents[1]
OMARCHY = Path(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy"))
CACHE = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "omabox-shots"


def patched_shell(work):
    """Commons and Ui copied next to the rig's shell.qml. Color reads SHOTS_THEME; the panel window never takes
    keyboard focus or pointer input and opens no dismiss twins on other monitors."""
    shell = work / "shell"
    shutil.rmtree(shell, ignore_errors=True)
    shell.mkdir(parents=True)
    for part in ("Commons", "Ui"):
        shutil.copytree(OMARCHY / "shell" / part, shell / part)
    shutil.copy(HERE / "shell.qml", shell / "shell.qml")
    for path in shell.rglob("*"):
        path.chmod(0o755 if path.is_dir() else 0o644)
    edits = {
        "Commons/Color.qml": [("readonly property string currentThemePath: ",
                               'readonly property string currentThemePath: Quickshell.env("SHOTS_THEME") || ')],
        "Ui/KeyboardPanel.qml": [
            ("WlrLayershell.keyboardFocus: open\n    ? (focusPrimed ? WlrKeyboardFocus.OnDemand : WlrKeyboardFocus.Exclusive)\n"
             "    : WlrKeyboardFocus.None\n", "WlrLayershell.keyboardFocus: WlrKeyboardFocus.None\n"),
            ("model: root.open ? Quickshell.screens : []", "model: []"),
        ],
    }
    for name, pairs in edits.items():
        path = shell / name
        text = path.read_text()
        for old, new in pairs:
            if old not in text:
                sys.exit(f"shots: {name} changed upstream, cannot patch: {old.strip()}")
            text = text.replace(old, new, 1)
        path.write_text(text)
    # The mask covers the whole screen; an empty Region makes the panel click-through.
    path = shell / "Ui/KeyboardPanel.qml"
    text = path.read_text()
    start = text.index("  mask: Region {\n    width: root.screenW\n    height: root.screenH\n  }")
    text = text[:start] + "  mask: Region {}" + text[start + len("  mask: Region {\n    width: root.screenW\n    height: root.screenH\n  }"):]
    path.write_text(text)
    return shell


def focused_screen():
    monitors = json.loads(subprocess.run(["hyprctl", "-j", "monitors"], capture_output=True, text=True).stdout)
    return next((m for m in monitors if m["focused"]), monitors[0])


def backdrop(theme):
    folder = OMARCHY / "themes" / theme / "backgrounds"
    pictures = sorted(p for p in folder.glob("*") if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"))
    return str(pictures[0]) if pictures else ""


def crop(empty, full, margin):
    """The panel plus margin, from the top of the screen so the bar icon shows above it."""
    a, b = Image.open(empty).convert("RGB"), Image.open(full).convert("RGB")
    box = ImageChops.difference(a, b).convert("L").point([0] * 25 + [255] * 231).getbbox()
    if not box:
        return b
    left, _, right, bottom = box
    # The panel is centred on the screen; anything else that changed only widens one side, so the narrower half wins.
    half = min(b.width / 2 - left, right - b.width / 2) + margin
    return b.crop((int(b.width / 2 - half), 0, int(b.width / 2 + half), min(b.height, bottom + margin)))


def shoot(shell, out, scenario, theme, screen):
    work = Path(tempfile.mkdtemp(prefix="omabox-shots-", dir=CACHE))
    home = work / "home"
    subprocess.run([sys.executable, str(HERE / "demo.py"), str(home)], check=True, capture_output=True)
    for name in ("fontconfig",):
        source = Path.home() / ".config" / name
        if source.exists():
            (home / ".config" / name).symlink_to(source)
    # Short: Quickshell's IPC socket lives under it and AF_UNIX paths stop at 108 bytes.
    runtime = Path(os.environ["XDG_RUNTIME_DIR"]) / f"oshots{os.getpid()}"
    runtime.mkdir(mode=0o700, exist_ok=True)
    (runtime / "hypr").symlink_to(Path(os.environ["XDG_RUNTIME_DIR"]) / "hypr")
    env = {**os.environ, "HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"),
           "XDG_STATE_HOME": str(home / ".local/state"), "XDG_CACHE_HOME": str(home / ".cache"),
           "XDG_RUNTIME_DIR": str(runtime),
           "WAYLAND_DISPLAY": str(Path(os.environ["XDG_RUNTIME_DIR"]) / os.environ.get("WAYLAND_DISPLAY", "wayland-1")),
           "SHOTS_THEME": str(OMARCHY / "themes" / theme), "SHOTS_SCENARIO": scenario, "SHOTS_PLUGIN": str(PLUGIN),
           "SHOTS_SCREEN": screen["name"], "SHOTS_BACKDROP": backdrop(theme)}
    log = open(work / "qs.log", "w")
    rig = subprocess.Popen(["qs", "-p", str(shell)], env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        time.sleep(2.2)
        subprocess.run(["grim", "-o", screen["name"], str(work / "empty.png")], check=True)
        time.sleep(3.0 if scenario != "add" else 3.4)
        subprocess.run(["grim", "-o", screen["name"], str(work / "full.png")], check=True)
    finally:
        rig.terminate()
        rig.wait(timeout=10)
        shutil.rmtree(runtime, ignore_errors=True)
    shot = crop(work / "empty.png", work / "full.png", margin=int(36 * screen["scale"]))
    target = out / f"{scenario}-{theme}.png"
    shot.save(target, optimize=True)
    problems = [line.strip() for line in (work / "qs.log").read_text().splitlines()
                if "omabox" in line.lower() and any(k in line for k in ("TypeError", "ReferenceError", "Cannot", "error"))]
    shutil.rmtree(work, ignore_errors=True)
    print(target, f"({shot.width}x{shot.height})")
    for line in problems[:5]:
        print("  ", line)


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    out = Path(sys.argv[1]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    shell = patched_shell(CACHE)
    monitors = json.loads(subprocess.run(["hyprctl", "-j", "monitors"], capture_output=True, text=True).stdout)
    wanted = os.environ.get("SHOTS_SCREEN")
    screen = next((m for m in monitors if m["name"] == wanted), None) or focused_screen()
    for spec in sys.argv[2:]:
        scenario, _, theme = spec.partition(":")
        shoot(shell, out, scenario, theme or "tokyo-night", screen)


if __name__ == "__main__":
    main()
