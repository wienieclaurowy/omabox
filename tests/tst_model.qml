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

  function test_clip_cuts_long_text_without_splitting_a_pair() {
    compare(Model.clip("short", 10), "short")
    compare(Model.clip("abcdefghij", 5), "abcd\u2026")
    compare(Model.clip("abc\ud83d\ude00x", 5), "abc\u2026")
    compare(Model.clip(new Array(100001).join("x"), Model.MESSAGE_CHARS).length, Model.MESSAGE_CHARS)
    verify(Model.MESSAGE_CHARS >= Model.ACTION_SHOWN_MAX + 200)
  }

  function test_a_notification_with_a_bad_timestamp_still_opens() {
    var row = { file: "1-1.json", app: "Chat", summary: "Hello", body: "Text" }
    compare(Model.noteAsItem(Object.assign({ timestamp: 1700000000000 }, row), english).published, "2023-11-14T22:13:20.000Z")
    compare(Model.noteAsItem(Object.assign({ timestamp: "not a date" }, row), english).published, "")
    compare(Model.noteAsItem(Object.assign({ timestamp: 1e20 }, row), english).published, "")
  }

  function test_x_replies_only_for_posts_of_x_sources() {
    var profiles = { "Rowan on X": { name: "Rowan" } }
    var link = "https://x.com/rowanvale/status/100"
    verify(Model.repliesAvailable({ source: "Rowan on X", link: link }, profiles))
    verify(!Model.repliesAvailable({ source: "Blog", link: link }, profiles))
    verify(!Model.repliesAvailable({ source: "Rowan on X", link: link }, undefined))
    verify(Model.repliesAvailable({ source: "Blog", link: "https://news.ycombinator.com/item?id=1" }, profiles))
  }

  function test_bounded_output_past_its_limit_is_an_error() {
    compare(Model.splitCliOutput("::overflow", english).code, 1)
    compare(Model.splitCliOutput("::overflow", english).text, english.t("cli.outputTooLarge"))
    compare(Model.splitCliOutput("{}::exit 0", english).text, "{}")
    var argv = Model.bounded(["head", "--", "/x"], 100, 5)
    compare(argv.slice(0, 3), ["python3", "-I", "-c"])
    verify(argv[3].indexOf("posix_spawnp") > 0)
    compare(argv.slice(4), ["100", "5", "--", "head", "--", "/x"])
    compare(Model.capped(["mpv"], 10).slice(4), ["10", "0", "--", "mpv"])
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

  function repeat(text, count) { return new Array(count + 1).join(text) }
  function longestRun(html) {
    var runs = html.replace(/<[^>]*>/g, "").split(/[ ​]/)
    return Math.max.apply(null, runs.map(function(run) { return run.length }))
  }

  function test_rendered_markup_keeps_ordinary_posts_whole() {
    var essay = repeat("<p>" + repeat("Calm words about a quiet river, <b>bold</b> and <a href=\"https://example.com/a\">linked</a>. ", 8)
      + "</p>", 200)
    compare(Model.boundMarkup(essay), essay)
    var comment = "<table width=\"100%\" cellspacing=\"0\" cellpadding=\"0\" class=\"comment\"><tr><td class=\"face\" valign=\"top\">"
      + "<img src=\"omabox-avatar:0123456789abcdef0123.png\"></td><td class=\"cell\" valign=\"top\"><p class=\"who\"><b>Fern</b> "
      + "<span class=\"meta\">@fern · <a href=\"https://x.com/fern/status/1\">Sep 20, 14:05</a></span></p><p>"
      + repeat("A reply of some length. ", 8) + "</p></td></tr></table>"
    var thread = repeat(comment, 300)
    compare(Model.boundMarkup(thread), thread)
    compare(Model.boundMarkup("<p>café 中文 😀 &amp; done</p>"), "<p>café 中文 😀 &amp; done</p>")
  }

  function test_rendered_markup_breaks_long_runs_across_inline_tags() {
    var word = Model.boundMarkup("<p>" + repeat("a", 600) + "</p>")
    compare(word, "<p>" + repeat("a", 256) + "​" + repeat("a", 256) + "​" + repeat("a", 88) + "</p>")
    var fragments = Model.boundMarkup("<p>" + repeat("<b>ab</b><i>cd</i>", 300) + "</p>")
    verify(fragments.indexOf("​") > 0)
    compare(longestRun(fragments), Model.MARKUP_RUN)
    var spaced = "<p>" + repeat("<b>ab</b> <i>cd</i> ", 300) + "</p>"
    compare(Model.boundMarkup(spaced), spaced)
    var broken = "<p>" + repeat(repeat("a", 200) + "​", 5) + "</p>"
    compare(Model.boundMarkup(broken), broken)
    compare(longestRun(Model.boundMarkup("<p>" + repeat("&amp;", 600) + "</p>").replace(/&amp;/g, "&")), Model.MARKUP_RUN)
    compare(longestRun(Model.boundMarkup("<p>" + repeat("中", 600) + "</p>")), Model.MARKUP_RUN)
  }

  function test_rendered_markup_never_parts_a_character_or_a_mark() {
    var marks = Model.boundMarkup("<p>" + repeat("a", 256) + "́́b" + repeat("c", 10) + "</p>")
    compare(marks, "<p>" + repeat("a", 256) + "́́​b" + repeat("c", 10) + "</p>")
    var emoji = Model.boundMarkup("<p>" + repeat("😀", 300) + "</p>")
    verify(!/[\ud800-\udbff]​|​[\udc00-\udfff]/.test(emoji))
    verify(emoji.indexOf("​") > 0)
    var family = Model.boundMarkup("<p>" + repeat("👩‍👧", 200) + "</p>")
    verify(family.indexOf("‍​") < 0)
    var skin = Model.boundMarkup("<p>" + repeat("a", 256) + "👋🏽" + "</p>")
    compare(skin, "<p>" + repeat("a", 256) + "​👋🏽</p>")
  }

  function test_rendered_markup_is_cut_past_the_layout_limits() {
    var items = Model.boundMarkup("<ul>" + repeat("<li>a</li>", Model.MARKUP_LIST_ITEMS + 500) + "</ul><p>after</p>")
    compare(items.split("<li>").length - 1, Model.MARKUP_LIST_ITEMS)
    verify(items.indexOf("after") < 0)
    compare(Model.boundMarkup(repeat("<table><tr><td>", 6) + "x"), repeat("<table><tr><td>", 3))
    compare(Model.boundMarkup(repeat("<div>", 100) + "x").split("<div>").length - 1, Model.MARKUP_DEPTH)
    var pictures = Model.boundMarkup("<p>" + repeat("<img src=\"omabox-img:0123456789abcdef0123.png\" width=\"1\" height=\"1\">", 1000) + "</p>")
    compare(pictures.split("<img").length - 1, Model.MARKUP_IMAGES)
    var text = Model.boundMarkup("<p>" + repeat("word ", 200000) + "</p>")
    verify(text.length < 500000)
    verify(/^<p>word( word)+$/.test(text), text.slice(-20))
    var wide = Model.boundMarkup("<p>" + repeat("\u4e2d", 1000000))
    verify(wide.length > 100000 && wide.length < Model.MARKUP_COST / 2 + 1000, wide.length)
    compare(longestRun(wide), Model.MARKUP_RUN)
    var emoji = Model.boundMarkup("<p>" + repeat("😀 ", 5000) + "</p>")
    verify((emoji.length / 3) <= Model.MARKUP_COST / Model.COST_EMOJI)
    var word = Model.boundMarkup("<p>" + repeat("a", 2000000))
    verify(word.length > 300000 && word.length < Model.MARKUP_COST + 2000, word.length)
    compare(word.slice(-1), "\u200b")
    compare(Model.boundMarkup("<p>a</p><b"), "<p>a</p>")
    var switched = Model.boundMarkup("<b>" + repeat("\u4e2d", (Model.MARKUP_COST - Model.COST_HEAVY_TAG) / 2) + "</b> word more")
    compare(switched.slice(-5), "\u4e2d</b>")
  }

  function test_rendered_markup_bounds_a_post_of_an_older_release() {
    var old = "<ul>" + repeat("<li>a</li>", 25000) + "</ul>"
    var rendered = Model.renderHtml(old, "/cache", 600, { avatar: 30, gap: 10, pad: 8, mini: 22 })
    compare(rendered.split("<li>").length - 1, Model.MARKUP_LIST_ITEMS)
  }
}
