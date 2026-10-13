# Searching posts from the Omarchy menu

`omabox pick [QUERY]` shows the newest 300 posts that match QUERY in the
Omarchy menu's select mode. Without a query, it shows all posts. Each row is
the post title, with the source and date underneath. Unread posts have a `●`
and read-later posts have a bookmark. The post you pick opens in the Omabox
reader. Filter, search and snooze are cleared so the post is visible. Press
Escape to close the menu without opening anything.

Like every Omarchy menu, the rows reach the menu as command arguments, so other
accounts on this computer can see them briefly. If you share the computer, use
the search in the panel (`/`) instead.

`omabox search [QUERY] [--json]` is the same search, printed to the terminal.
A post matches when every word of the query appears in its title, source or
text. Case is ignored.

The reader can also open a post by id over IPC:
`omarchy-shell omabox openPost <id>`.

## Adding it to the menu and a key

The menu and the key run `omabox`, so put the command on your `PATH` first (see the README).

The menu can't discover Omabox by itself, so add this entry to
`~/.config/omarchy/extensions/omarchy-menu.jsonc`, inside the outer braces:

```jsonc
"omabox-search": {"icon": "󰍉", "label": "Omabox: search posts", "action": "omabox pick", "description": "Find a post and open it in the reader"},
```

Add this keybinding to `~/.config/hypr/bindings.lua`:

```lua
o.bind("SUPER + CTRL + SHIFT + M", "Omabox search", "omabox pick")
```

`omabox pick --help` prints both snippets. `omabox doctor` reports when the
menu entry is missing.
