# Omabox

A quiet inbox for the Omarchy bar: feeds delivered once a day, plus a 7-day history of desktop notifications,
in one panel. `bin/omabox` is a single-file, stdlib-only Python CLI that owns all state and fetching. The QML
at the repo root is the plugin (the repo root is the plugin directory); the panel changes data only through
the CLI.

## Build, run, live test

- Nothing to build. Link the clone as the plugin and restart the shell (README, "Development").
- Restart the shell after every QML edit: hot reload leaves stale panel state.
- Open a view without typing: `omarchy-shell omabox toggleView <feed|notifications|sources>`, and
  `omarchy-shell omabox read <n>` for post n in the reader. Then take a screenshot.
- `omabox doctor` checks delivery, sources, cache and tools; `omabox fetch --all` fetches now.
- README screenshots come from `tools/screenshots/shots.py`: a second, sandboxed Quickshell with invented
  data. Use it for visual checks that must not touch the live inbox.

## Verify

`./verify` (about 25 s): ruff, a QML syntax check, the manifest, and the whole test suite, which also runs
the catalog check (`tests/i18n_check.py i18n --sources .`) and `tests/tst_model.qml` over `Model.js`.

## Gotchas

- `bin/omabox` must start on Python 3.11, but the test suite needs 3.12. `ruff.toml` checks 3.11 syntax only;
  a change to imports, codecs or stdlib calls needs one real run of the CLI in a Python 3.11 container.
- Never drive the live panel with synthetic keystrokes. Only one popout is open at a time, so when the panel
  closes mid-test the keys land in another window. Use the IPC calls above.
- Plain `qml` and `qmltestrunner` cannot load `qs.Commons`, and Quickshell cannot `grabToImage` off-screen.
  Logic that needs a test goes into `Model.js`; looks are checked in the live or the sandboxed shell.
- The reading font tags every file as weight 80: set `font.styleName` ("Regular" or "Bold") or Qt draws bold.
- By design, not bugs: no live or instant mode, no counters of likes or views, arrow keys swallowed in the
  panel (vim keys only), delivery notifications at normal urgency so do-not-disturb can hold them.

## Done means

- `./verify` passes, and a behavior change has a test in `tests/test_omabox.py`.
- A new string is in `i18n/en.json` and all 11 catalogs, and the catalog check reports 0 errors.
- A panel change was seen in the running shell after a restart; the README says what the software now does.
