import QtQuick
import QtTest
import "../Model.js" as Model
import "../Plural.js" as Plural

// Run by test_omabox.py (ModelJsTest) through qmltestrunner, which has no Quickshell for Tr.qml: `english` stands in
// for it over i18n/en.json (file reads need QML_XHR_ALLOW_FILE_READ=1).
TestCase {
  name: "Model"

  QtObject {
    id: english
    readonly property var strings: {
      var request = new XMLHttpRequest()
      request.open("GET", Qt.resolvedUrl("../i18n/en.json"), false)
      request.send()
      return JSON.parse(request.responseText)
    }
    readonly property var locale: Qt.locale("en-US")
    function t(key) { var value = strings[key]; return typeof value === "object" ? value.other : value }
    function tn(key, count) { return Plural.pick(strings[key], "en", count) }
    function formatNumber(value) { return String(value) }
  }

  // Marks each translated word, to show which parts of the markup were swapped.
  QtObject {
    id: marked
    readonly property var locale: Qt.locale("de-DE")
    function t(key) { return "<" + english.t(key) + ">" }
    function tn(key, count) { return "<" + english.tn(key, count) + ">" }
    function formatNumber(value) { return String(value) }
  }

  function test_bounded_output_past_its_limit_is_an_error() {
    compare(Model.splitCliOutput("::overflow", english).code, 1)
    compare(Model.splitCliOutput("::overflow", english).text, english.t("cli.outputTooLarge"))
    compare(Model.splitCliOutput("{}::exit 0", english).text, "{}")
    var argv = Model.bounded(["head", "--", "/x"], 100, 5)
    compare(argv.slice(0, 2), ["bash", "-c"])
    compare(argv.slice(3), ["--", "100", "5", "head", "--", "/x"])
  }

  function test_notification_action_runs_only_on_the_second_o() {
    var row = { file: "1760000000000-1.json", execArgv: JSON.stringify(["sh", "-c", "echo planted\n"]) }
    var first = Model.actionStep(row, "", "", english)
    compare(first.run, null)
    compare(first.pending, row.file)
    compare(first.message, 'o again to run: sh -c "echo planted\\n"')
    var second = Model.actionStep(row, first.pending, first.message, english)
    compare(second.run, ["sh", "-c", "echo planted\n"])
    compare(second.pending, "")
    // the line was cleared or shows something else, or the cursor is on another notification: shown again, not run
    compare(Model.actionStep(row, first.pending, "", english).run, null)
    compare(Model.actionStep(row, first.pending, "Copied", english).run, null)
    var other = { file: "1760000000001-1.json", execArgv: row.execArgv }
    compare(Model.actionStep(other, first.pending, first.message, english).run, null)
    compare(Model.actionStep({ file: "x" }, "", "", english).message, "This notification has no action.")
  }

  function test_command_line_is_whole_and_shows_hidden_characters() {
    compare(Model.commandLine(["omarchy-launch-webapp", "https://example.com/a", "x y"]),
            "omarchy-launch-webapp https://example.com/a \"x y\"")
    var long = Model.commandLine(["sh", "-c", "a".repeat(300) + " middle " + "b".repeat(200)])
    verify(long.indexOf(" middle ") > 0)
    compare(long.length, 6 + 300 + 8 + 200 + 2)
    compare(Model.commandLine(["echo", "safe\u202e\u200bgnp.exe"]), 'echo "safe\\u202e\\u200bgnp.exe"')
  }

  function test_an_action_too_long_to_show_is_not_run() {
    var row = { file: "1760000000000-1.json", execArgv: JSON.stringify(["sh", "-c", "x".repeat(700)]) }
    var first = Model.actionStep(row, "", "", english)
    compare(first.run, null)
    compare(first.pending, "")
    verify(first.message.indexOf("too long") > 0)
    compare(Model.actionStep(row, row.file, first.message, english).run, null)
  }

  // bin/omabox replies_markup and quote_markup output, as stored in items.json.
  readonly property string storedReplies: '<hr class="rule"><p class="section">Comments <span class="count">3</span></p>'
    + '<p class="meta">Top replies on X, the author\'s threads first · fetched Sep 20, 14:05</p>'
    + '<table class="comment"><tr><td class="face"></td><td class="cell"><p class="who"><b>Rowan</b> <span class="meta">@rowan · '
    + '<a href="https://x.com/rowan/status/1">Sep 20, 13:58</a></span></p>'
    + '<p class="replyto">Replying to <a href="https://x.com/a">@a</a>, <a href="https://x.com/b">@b</a> and 4 others</p>'
    + '<p class="said">Fair point.</p></td></tr></table>'
    + '<p class="who"><span class="opname">Tides</span> <span class="badge">AUTHOR</span> <span class="meta">'
    + '<a href="https://www.reddit.com/r/x/comments/1/a/b">open</a></span></p>'
    + '<p>site.example · <a href="https://news.ycombinator.com/item?id=1">Discussion on Hacker News</a></p>'

  function test_english_markup_is_unchanged() {
    var item = { id: "a", html: "<p>Post</p>", replies_html: storedReplies }
    compare(Model.withReplies(item, false, english).html, "<p>Post</p>" + storedReplies)
  }

  function test_markup_words_are_swapped_and_names_kept() {
    var html = Model.withReplies({ id: "a", html: "", replies_html: storedReplies }, true, marked).html
    verify(html.indexOf("&lt;Refreshing comments…&gt;") > 0, html)
    verify(html.indexOf('<p class="section">&lt;Comments&gt; <span class="count">3</span>') > 0, html)
    verify(html.indexOf("&lt;%1 · fetched %2&gt;") < 0 && html.indexOf("&lt;&lt;Top replies on X") > 0, html)
    verify(html.indexOf('<p class="replyto">&lt;Replying to &lt;<a href="https://x.com/a">@a</a>&lt;, &gt;'
      + '<a href="https://x.com/b">@b</a> and &lt;4 others&gt;&gt;&gt;</p>') > 0, html)
    verify(html.indexOf('<span class="badge">&lt;AUTHOR&gt;</span>') > 0, html)
    verify(html.indexOf('<a href="https://www.reddit.com/r/x/comments/1/a/b">&lt;open&gt;</a>') > 0, html)
    verify(html.indexOf("&lt;Discussion on Hacker News&gt;</a>") > 0, html)
    verify(html.indexOf(">Sep 20, 13:58<") < 0, html)
  }

  function test_fill_never_refills_a_value() {
    compare(Model.fill("%1 and %2", ["%2", "b"]), "%2 and b")
  }

  function test_relative_time_and_counts() {
    var now = new Date(2026, 9, 14, 12, 0)
    compare(Model.relativeTime(new Date(2026, 9, 14, 11, 55).toISOString(), now, english), "5m ago")
    compare(Model.relativeTime(new Date(2026, 8, 20, 9, 0).toISOString(), now, english), "Sep 20")
    compare(Model.relativeTime(new Date(2025, 8, 20, 9, 0).toISOString(), now, english), "Sep 20 2025")
    compare(Model.muteSummary({ mute: ["a"], x_hidden: { reposts: true } }, english), "  ·  1 mute rule  ·  no reposts")
    compare(Model.weekdayOptions(english)[0].label, "Mon")
    compare(Model.weekdayOptions(english)[6].tooltip, "Sunday (w cycles)")
    compare(Model.hintEntries("feed", "list", false, english)[0], { key: "j/k", label: "move" })
  }

  function test_read_posts_recede_on_every_theme() {
    var card = Qt.rgba(0.96, 0.9, 0.83, 1)
    var lowFg = Qt.rgba(0.62, 0.31, 0.36, 1)
    var low = Model.contrastRatio(Model.readShade(lowFg, card), card)
    verify(low >= 2.4 && low < Model.contrastRatio(lowFg, card) - 1, low)
    var high = Model.contrastRatio(Model.readShade(Qt.rgba(0, 0, 0, 1), Qt.rgba(1, 1, 1, 1)), Qt.rgba(1, 1, 1, 1))
    verify(high >= 4.5 && high < 4.7, high)
  }

  function test_input_field_editing() {
    compare(Model.spliceField("hello", 5, 5, " world", 100), { text: "hello world", cursor: 11 })
    compare(Model.spliceField("hello", 1, 4, "", 100), { text: "ho", cursor: 1 })
    compare(Model.spliceField("ab", 1, 1, "x\ny\tz", 100), { text: "ax y zb", cursor: 6 })
    compare(Model.spliceField("abc", 3, 3, "defgh", 5), { text: "abcde", cursor: 5 })
    compare(Model.spliceField("abc", 3, 0, "Z", 5), { text: "Z", cursor: 1 })
    compare(Model.spliceField("", 0, 0, "a\ud83d\ude00", 2), { text: "a", cursor: 1 })
    compare(Model.charStep("a\ud83d\ude00b", 3, false), 1)
    compare(Model.charStep("a\ud83d\ude00b", 1, true), 3)
    compare(Model.charStep("ab", 0, false), 0)
    compare(Model.wordStart("foo bar  ", 9), 4)
    compare(Model.wordStart("foo ", 4), 0)
    compare(Model.wordStart("foo bar", 3), 0)
  }
}
