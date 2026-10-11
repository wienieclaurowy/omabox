"""Writes a sample Omabox setup into a sandbox home for the screenshot harness: sources, delivered posts and a
notification history.

    python3 demo.py SANDBOX-HOME
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

home = Path(sys.argv[1]).resolve()
os.environ.update(HOME=str(home), XDG_CONFIG_HOME=str(home / ".config"), XDG_STATE_HOME=str(home / ".local/state"),
                  XDG_CACHE_HOME=str(home / ".cache"))

import importlib.machinery  # noqa: E402
import importlib.util  # noqa: E402

BIN = Path(__file__).resolve().parents[2] / "bin" / "omabox"
loader = importlib.machinery.SourceFileLoader("omabox", str(BIN))
spec = importlib.util.spec_from_loader("omabox", loader)
assert spec
omabox = importlib.util.module_from_spec(spec)
loader.exec_module(omabox)

now = datetime.now(timezone.utc).replace(microsecond=0)


def ago(**delta):
    return (now - timedelta(**delta)).strftime("%Y-%m-%dT%H:%M:%SZ")


def para(*texts):
    return "".join(f"<p>{text}</p>" for text in texts)


SOURCES = [
    ("Lantern", "https://github.com/lantern-wm/lantern/releases.atom", "daily"),
    ("Field Notes", "https://fieldnotes.example/feed.xml", "daily"),
    ("Quarry Bench", "https://www.youtube.com/feeds/videos.xml?channel_id=UCq7rWm2Lk9vBfT4xNcD8sYe", "weekly"),
    ("Ada Lumen on X", f"{omabox.RSSHUB_BASE}/twitter/user/ada_lumen", "daily"),
    ("Fernwick", "https://bsky.app/profile/fernwick.bsky.social/rss", "daily"),
    ("Tidepool", "https://mastodon.social/@tidepool.rss", "daily"),
    ("Hacker News", "https://hnrss.org/frontpage?points=300", "daily"),
]

# (source, title, html, published, unread, later)
POSTS = [
    ("Lantern", "v2.3.0", para(
        "Lantern 2.3 brings window groups you can name, a calmer focus animation and a much faster start.",
        "What is new:", "<ul><li>Named window groups that survive a restart</li><li>Per-monitor gaps</li>"
        "<li>A <code>lantern doctor</code> command that explains odd configs</li></ul>",
        "What is fixed:", "<ul><li>Fullscreen video no longer flickers on mixed refresh rates</li>"
        "<li>Scratchpads keep their size after a resolution change</li></ul>"), ago(hours=3), True, False),
    ("Field Notes", "The case for reading things once a day", para(
        "I moved every feed I follow into one morning delivery. For the first week I kept reaching for the refresh "
        "button that was no longer there. By the second week the reaching stopped.",
        "What surprised me most was not the time it saved, but how much more I remembered of what I read. "
        "A dozen posts read slowly with a coffee stick in a way that a hundred skimmed between meetings never did.",
        "Here is how the setup works, what I gave up, and the two sources I ended up dropping for good."),
     ago(hours=2), True, True),
    ("Quarry Bench", "Restoring a 1940s hand plane, start to finish", para(
        "Rust, a cracked tote and a sole that was anything but flat. Forty minutes later it takes whisper-thin "
        "shavings again. Chapters: tearing down, rust removal, flattening the sole, a new tote from walnut offcuts."),
     ago(hours=5), True, False),
    ("Ada Lumen on X", "Finally finished my rain theme for Omarchy. Soft greys, one warm accent, and the clock "
     "turns blue when it is about to pour.", "Finally finished my rain theme for Omarchy. Soft greys, one warm "
     "accent, and the clock turns blue when it is about to pour.", ago(hours=4), True, False),
    ("Ada Lumen on X", "Small thing that made my week: the keyboard light now fades out with the screen at night.",
     "Small thing that made my week: the keyboard light now fades out with the screen at night.",
     ago(hours=9), False, False),
    ("Fernwick", "Morning walk along the canal: three herons, one very confident duck, zero notifications.",
     "Morning walk along the canal: three herons, one very confident duck, zero notifications.",
     ago(hours=6), True, False),
    ("Tidepool", "We just shipped offline maps. Download a region once and find your way without a signal.",
     "We just shipped offline maps. Download a region once and find your way without a signal.",
     ago(hours=7), False, False),
    ("Hacker News", "Show HN: A tiny e-ink dashboard that only updates at sunrise", para(
        "I wanted something on my desk that tells me the weather, my first meeting and nothing else."),
     ago(hours=8), True, False),
    ("Hacker News", "The quiet return of the RSS reader", para("Comments: 214"), ago(hours=10), False, False),
    ("Field Notes", "A desk that only does one thing", para(
        "My second monitor now shows exactly one window. It took three tries to get there."),
     ago(days=2), False, False),
    ("Lantern", "v2.2.4", para("<b>Fixes</b>", "<ul><li>Crash when the last monitor was unplugged</li></ul>"),
     ago(days=4), False, False),
]

state = omabox.load_state()
stamp = ago(minutes=40)
marks = {}
for name, url, cadence in SOURCES:
    entries = []
    for number, (source, title, html, published, unread, later) in enumerate(POSTS):
        if source != name:
            continue
        guid = f"demo-{number}"
        entries.append({"guid": guid, "title": title, "link": f"https://example.com/post/{number}",
                        "published": published, "html": html})
        marks[omabox.item_id(name, guid)] = (unread, later)
    omabox.merge(state, name, entries, stamp)
    state["icons"][name] = {"glyph": omabox.glyph_for(url) or chr(omabox.GLYPHS["rss"])}
    state["fetched"][name] = stamp
for item in state["items"]:
    unread, later = marks[item["id"]]
    item["read"] = not unread
    if later:
        item["later"] = True
state["delivered"] = stamp
omabox.save_sources([{"name": n, "url": u, "cadence": c} for n, u, c in SOURCES])
omabox.save_state(state)

history = home / ".local/state/omarchy/notifications/history"
history.mkdir(parents=True, exist_ok=True)
NOTES = [
    ("Calendar", "Design review in 10 minutes", "Room 3 and on video. Bring the sketches from Tuesday.", 12, ""),
    ("Signal", "Mira", "Are we still on for climbing on Saturday?", 35, ""),
    ("Steam", "Download complete", "Ostriv is ready to play.", 80, ""),
    ("Omabox", "Omabox: 6 new posts", "Lantern, Field Notes, Quarry Bench, Ada Lumen on X, Fernwick, Hacker News", 40, "󰚇"),
    ("Battery", "Headphones at 15%", "About two hours of listening left.", 190, ""),
    ("Thunderbird", "Invoice 2026-10", "Your hosting invoice is ready. Nothing to pay: it is covered by credit.", 300, ""),
    ("Updates", "System up to date", "42 packages updated. No restart needed.", 520, ""),
    ("Calendar", "Dentist tomorrow at 9:30", "Remember to leave 20 minutes early: roadworks on the bridge.", 610, ""),
    ("Signal", "Jonas", "Sent you the photos from the lake.", 700, ""),
    ("Screenshot", "Screenshot saved", "Copied to the clipboard and saved to Pictures.", 760, ""),
    ("Timer", "Tea is ready", "Four minutes are up.", 830, ""),
]
for number, (app, summary, body, minutes, glyph) in enumerate(NOTES, 1):
    stamp_ms = int((now - timedelta(minutes=minutes)).timestamp() * 1000)
    note = {"id": number, "originalId": number, "app": app, "appIcon": "", "summary": summary, "body": body,
            "image": "", "glyph": glyph, "execArgv": "", "urgency": 1, "expireTimeout": -1, "timestamp": stamp_ms}
    (history / f"{stamp_ms}-{number}.json").write_text(json.dumps(note))
print(f"{len(state['items'])} posts, {len(NOTES)} notifications")
