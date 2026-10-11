# Omabox

Omabox is a quiet inbox for the [Omarchy](https://omarchy.org) bar. It delivers your feeds once a day, at a time
you choose, instead of all day long. It also keeps a 7-day history of your desktop notifications. Both live in
one panel behind one bar icon.

It shows no likes, views or repost counts anywhere, so you read posts for what they say.

## Why once a day

Omabox is built to be distraction-free. Most feed readers refresh all day long and show a count that keeps
climbing, so you keep checking them. Omabox collects new posts quietly and hands them over at most once a day,
at the time you choose, like a morning paper. Between deliveries nothing new arrives, so there is nothing to
check.

This is on purpose, so Omabox has no mode that shows posts the moment they are published. Instead you can:

- pick the delivery time, for example 18:00 for an evening read (`-`/`+` in the Sources view),
- set busy sources to weekly, or pause them,
- fetch everything right now with `omabox fetch --all` when you really need to.

If you want every post as soon as it appears, a regular feed reader will suit you better.

## Features

- **Once-a-day delivery.** New posts arrive at your delivery time (08:00 by default), with one notification
  that names the sources. Sources can also be weekly or paused. A delivery missed while the computer was off
  or asleep comes as soon as it is back.
- **Many kinds of sources.** Any RSS or Atom feed, plus web pages with a feed link, GitHub releases, YouTube
  channels, Bluesky, Mastodon, Reddit, Hacker News and, optionally, X profiles. Paste a page address and
  Omabox finds the feed.
- **A reader.** Posts open in the panel with pictures, link previews and videos (played in mpv). Feeds that
  only send a summary can fetch the whole article. X posts show their replies under them.
- **Calm tools.** Snooze a post until later or tomorrow, keep a read-later list, mute words or patterns per
  source, search everything, and mark old posts read in one step.
- **Notification history.** Omarchy keeps its last 10 notifications; Omabox keeps every one for 7 days, with
  search, filters and do-not-disturb.
- **Keyboard first.** Every action has a key. Press `?` in the panel to show them.

## Requirements

- Omarchy with the plugin shell
- Python 3.11 or newer as `python3` (Omarchy ships it)

Optional:

- `mpv` to play videos, and a picture viewer such as `imv` to open pictures
- `wl-copy` to copy links
- `podman` or `docker` for X sources (see [X sources](#x-sources))

## Install

```sh
omarchy plugin add https://github.com/wienieclaurowy/omabox.git --enable
```

The icon appears in the bar. The first delivery starts within a minute and brings two starter sources:
Omarchy's releases and DHH's blog. Remove them or add your own in the panel's Sources view.

To open the panel from a key, add a line like this to `~/.config/hypr/bindings.lua`, with any free key:

```lua
o.bind("SUPER + SHIFT + I", "Omabox", "omarchy-shell shell toggle io.github.wienieclaurowy.omabox")
```

### The `omabox` command

Most of what the panel does can also be done from a terminal with the `omabox` command, which ships with the
plugin. To put it on your `PATH`:

```sh
ln -s ~/.config/omarchy/plugins/io.github.wienieclaurowy.omabox/bin/omabox ~/.local/bin/omabox
```

A few things are only in the command:

- `omabox pause 3d` holds deliveries for a while (`omabox pause off` resumes them).
- `omabox opml export` and `omabox opml import FILE` move your sources from or to another reader.
- `omabox pick` searches your posts from the Omarchy menu. See [docs/launcher.md](docs/launcher.md).
- `omabox doctor` checks the setup and lists any feeds that failed.

Run `omabox --help` for the full list.

## Using it

Click the icon to open the feed. Middle-click it to mark everything read. A dot on the icon means unread posts.

The panel has three views: **Feed**, **Notifications** and **Sources** (keys `1`, `2`, `3`).

- In the feed, `j`/`k` move, `l` opens a post, `o` opens it in the browser, `z` snoozes it and `m` adds it
  to read later.
- In Sources, `n` adds a source, `c` changes its cadence, `m` sets mute words and `-`/`+` move the delivery
  time.
- `?` shows every key for the view you are in.

### Settings

Set these in the widget's entry in `~/.config/omarchy/shell.json`:

| Setting | Default | What it does |
|---|---|---|
| `readingFont` | `iA Writer Quattro S` | Font for post text in the reader |
| `readingMeasure` | `70` | Reader line length, in characters (45 to 100) |
| `readerFontDelta` | `0` | Reader text size, relative to the theme (`+`/`-` in the reader change it) |
| `hints` | `false` | Show the key hints line (`?` toggles it) |

## X sources

X has no public feeds, so Omabox reads X through [RSSHub](https://docs.rsshub.app), which runs locally in a
podman or docker container only while a fetch needs it. It needs your X login:

1. Sign in to x.com in your browser and copy the value of the `auth_token` cookie.
2. Save it, and nothing else, in `~/.config/omabox/x-token`, then run
   `chmod 600 ~/.config/omabox/x-token`.
3. Add an X profile in the Sources view, for example `https://x.com/someone`.

The first X fetch downloads the RSSHub image, which takes a minute. When X rejects the token, Omabox sends one
notification asking you to refresh it.

Reading X this way uses your own account's session, which X's terms do not allow. Your account could be
limited for it. Omabox fetches each X source once per delivery, and replies only when you open a post.

## Privacy

Omabox has no telemetry and no account. It talks only to the feeds you add, to the sites their posts link to
(for pictures, link previews and full articles), and, for X, to a local RSSHub container. Pictures, previews
and articles are never fetched from addresses on your local network, so a feed cannot use Omabox to reach your
router or other machines.

The notification history keeps the text of your notifications, which can include sign-in codes, for 7 days in
`~/.local/state/omabox/notifications`. `X` in the Notifications view clears it.

## Files

| Path | What is in it |
|---|---|
| `~/.config/omabox/sources.toml` | Your sources, written by the panel and the `omabox` command |
| `~/.config/omabox/x-token` | Your X token, if you use X sources |
| `~/.local/state/omabox/` | Posts, read state and the notification history |
| `~/.cache/omabox/` | Pictures and icons |

## Remove

```sh
omarchy plugin remove io.github.wienieclaurowy.omabox
rm -rf ~/.config/omabox ~/.local/state/omabox ~/.cache/omabox
rm -f ~/.local/bin/omabox
```

If you used X sources, also remove the RSSHub image:

```sh
podman rmi docker.io/diygod/rsshub:latest   # or: docker rmi docker.io/diygod/rsshub:latest
```

## Development

Run the tests with `python -m unittest discover -s tests`. To work on a clone, link it as the plugin and
restart the shell after QML changes:

```sh
ln -sfn "$PWD" ~/.config/omarchy/plugins/io.github.wienieclaurowy.omabox
omarchy restart shell
```

## License

[MIT](LICENSE)
