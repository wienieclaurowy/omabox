# Searching posts from the Omarchy menu

`omabox pick [QUERY]` opens the Omabox panel's search with QUERY already
typed, and works like a launcher: type to filter the posts, move with the arrow
keys, and press Enter to open the highlighted post in the reader. Press Escape
to close the panel without opening anything. The search clears the panel's
source filter and finds the query in a post's title, source and opening text.
Snoozed posts are not in the panel's list, so it does not find them.

The query reaches the panel over the shell's own IPC socket, and the posts
never leave the panel, so other accounts on this computer cannot read them from
the process list.

`omabox search [QUERY] [--json]` searches from the terminal instead. A post
matches when every word of the query appears in its title, source or text.
Case is ignored.

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
