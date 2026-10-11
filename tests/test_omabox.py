import argparse
import codecs
import contextlib
import http.server
import importlib.machinery
import importlib.util
import io
import ipaddress
import json
import os
import re
import socket
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest import mock
from datetime import datetime, timedelta, timezone
from pathlib import Path

BIN = Path(__file__).resolve().parent.parent / "bin" / "omabox"
loader = importlib.machinery.SourceFileLoader("omabox", str(BIN))
spec = importlib.util.spec_from_loader("omabox", loader)
omabox = importlib.util.module_from_spec(spec)
loader.exec_module(omabox)

ATOM_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>tag:github.com,2008:Repository/1/v4.0.4</id>
    <updated>2026-09-15T22:15:08Z</updated>
    <link rel="alternate" type="text/html" href="https://github.com/omacom/omarchy/releases/tag/v4.0.4"/>
    <title>v4.0.4</title>
    <content type="html">&lt;h2&gt;Fixes&lt;/h2&gt;&lt;ul&gt;&lt;li&gt;Fix webcam &lt;img src="https://t.example/p.gif"&gt;by &lt;a href="https://github.com/x"&gt;@x&lt;/a&gt;&lt;/li&gt;&lt;/ul&gt;</content>
  </entry>
  <entry>
    <id>tag:github.com,2008:Repository/1/v4.0.3</id>
    <updated>2026-09-01T10:00:00Z</updated>
    <link rel="alternate" type="text/html" href="https://github.com/omacom/omarchy/releases/tag/v4.0.3"/>
    <title>v4.0.3</title>
    <content type="html">&lt;p&gt;Older&lt;/p&gt;</content>
  </entry>
</feed>"""

RSS_FEED = b"""<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item>
    <title>Post &amp;amp; more</title>
    <link>https://example.com/post</link>
    <guid>post-1</guid>
    <pubDate>Sat, 26 Sep 2026 08:00:00 +0200</pubDate>
    <description>&lt;script&gt;alert(1)&lt;/script&gt;&lt;p onclick="x"&gt;Hello &lt;a href="javascript:bad()"&gt;there&lt;/a&gt;&lt;/p&gt;</description>
  </item>
</channel></rss>"""


YOUTUBE_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns:media="http://search.yahoo.com/mrss/" xmlns="http://www.w3.org/2005/Atom">
 <title>Quarry Bench</title>
 <entry>
  <id>yt:video:Zq3vKe8TbWo</id>
  <title>A Workbench Built From Scrap</title>
  <link rel="alternate" href="https://www.youtube.com/watch?v=Zq3vKe8TbWo"/>
  <published>2026-09-26T17:08:04+00:00</published>
  <media:group>
   <media:title>A Workbench Built From Scrap</media:title>
   <media:content url="https://www.youtube.com/v/Zq3vKe8TbWo?version=3" type="application/x-shockwave-flash" width="640" height="390"/>
   <media:thumbnail url="https://i2.ytimg.com/vi/Zq3vKe8TbWo/hqdefault.jpg" width="480" height="360"/>
   <media:description>Think of a hand tool &lt;any&gt; at all.
We made one.

Discuss on the forum: https://forum.example/topic/1643100/</media:description>
  </media:group>
 </entry>
</feed>"""

BLUESKY_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>@fernwick.bsky.social - Bluesky</title>
<item><link>https://bsky.app/profile/fernwick.bsky.social/post/3kx7fqm2pa1zt</link>
<description>If you&#39;re at the market, the bread stall is open!&#xA;&#xA;It closes in 5 hours.</description>
<pubDate>21 Sep 2026 18:04 +0000</pubDate>
<guid isPermaLink="false">at://did:plc:q4m2x7c9h3k5t8w1b6n0r2pz/app.bsky.feed.post/3kx7fqm2pa1zt</guid></item>
</channel></rss>"""


class SanitizeTest(unittest.TestCase):
    def test_drops_images_scripts_and_unsafe_links(self):
        body, text = omabox.sanitize('<script>x()</script><p onclick="y">Hi <img src="https://t/p.gif"><a href="javascript:z">link</a></p>')
        self.assertEqual(body, "<p>Hi link</p>")
        self.assertEqual(text, "Hi link")

    def test_keeps_http_links_and_flattens_headings(self):
        body, _ = omabox.sanitize('<h2>Fixes</h2><a href="https://a.b/?q=1&amp;r=2">x</a>')
        self.assertEqual(body, '<p class="h">Fixes</p><a href="https://a.b/?q=1&amp;r=2">x</a>')

    def test_closes_unbalanced_tags(self):
        body, _ = omabox.sanitize("<ul><li>one<li>two")
        self.assertEqual(body, "<ul><li>one<li>two</li></li></ul>")

    def test_escapes_text(self):
        body, text = omabox.sanitize("a &lt;b&gt; c")
        self.assertEqual(body, "a &lt;b&gt; c")
        self.assertEqual(text, "a <b> c")


class ParseTest(unittest.TestCase):
    def test_atom(self):
        entries = list(omabox.parse_feed(ATOM_FEED))
        self.assertEqual([e["title"] for e in entries], ["v4.0.4", "v4.0.3"])
        self.assertEqual(entries[0]["link"], "https://github.com/omacom/omarchy/releases/tag/v4.0.4")
        self.assertEqual(entries[0]["published"], "2026-09-15T22:15:08Z")
        self.assertIn("<h2>Fixes</h2>", entries[0]["html"])

    def test_atom_xhtml_content_and_blank_content(self):
        feed = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:x="http://www.w3.org/1999/xhtml">
 <entry><id>a</id><title type="xhtml"><div xmlns="http://www.w3.org/1999/xhtml">Tide <b>tables</b></div></title>
  <content type="xhtml">
   <div xmlns="http://www.w3.org/1999/xhtml"><p>Low water at <a href="https://example.com/t">noon</a>.</p><br/></div>
  </content></entry>
 <entry><id>b</id><title>Blank</title><content type="html">  </content><summary>Only the summary</summary></entry>
 <entry><id>c</id><title>Prefixed</title><content type="xhtml"><x:div><x:p>Kelp</x:p></x:div></content></entry>
</feed>"""
        first, second, third = omabox.parse_feed(feed)
        self.assertEqual(first["title"], "Tide tables")
        self.assertEqual(first["html"], '<div><p>Low water at <a href="https://example.com/t">noon</a>.</p><br></div>')
        self.assertEqual(second["html"], "Only the summary")
        self.assertEqual(third["html"], "<div><p>Kelp</p></div>")

    def test_rss_1_0(self):
        feed = b"""<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/"
  xmlns:dc="http://purl.org/dc/elements/1.1/">
 <channel rdf:about="https://example.com/"><title>Harbour Notes</title><link>https://example.com/</link></channel>
 <item rdf:about="https://example.com/ferry"><title>Ferry times</title><link>https://example.com/ferry</link>
  <description>&lt;p&gt;Summer timetable&lt;/p&gt;</description><dc:date>2026-09-20T07:30:00+02:00</dc:date></item>
</rdf:RDF>"""
        (entry,) = omabox.parse_feed(feed)
        self.assertEqual((entry["guid"], entry["title"], entry["link"]), ("https://example.com/ferry", "Ferry times", "https://example.com/ferry"))
        self.assertEqual(entry["published"], "2026-09-20T05:30:00Z")
        self.assertEqual(entry["html"], "<p>Summer timetable</p>")
        self.assertEqual(omabox.feed_title(feed), "Harbour Notes")
        self.assertEqual(omabox.feed_home(feed), "https://example.com/")

    def test_entries_without_guid_or_link_keep_apart(self):
        feed = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Gull count</title><description>Twelve</description><pubDate>Sat, 26 Sep 2026 08:00:00 +0000</pubDate></item>
<item><title>Gull count</title><description>Fourteen</description><pubDate>Sun, 27 Sep 2026 08:00:00 +0000</pubDate></item>
</channel></rss>"""
        entries = list(omabox.parse_feed(feed))
        self.assertTrue(all(entry["guid"] for entry in entries))
        self.assertEqual([entry["guid"] for entry in omabox.parse_feed(feed)], [entry["guid"] for entry in entries])
        state = omabox.load_state(Path(tempfile.mkdtemp()) / "missing.json")
        self.assertEqual(omabox.merge(state, "Gulls", entries, "2026-09-27T09:00:00Z"), 1)
        self.assertEqual(len(state["items"]), 2)

    def test_sloppy_xml_is_read(self):
        lead = b"\n  " + RSS_FEED
        self.assertEqual(next(omabox.parse_feed(lead))["guid"], "post-1")
        entities = RSS_FEED.replace(b"Post &amp;amp; more", b"Caf&eacute;&nbsp;notes & more")
        self.assertEqual(next(omabox.parse_feed(entities))["title"], "Caf\u00e9\u00a0notes & more")
        cdata = RSS_FEED.replace(b"<link>https://example.com/post</link>",
                                 b"<link><![CDATA[https://example.com/p?a=1&b=2]]></link>").replace(b"<guid>post-1</guid>", b"&nbsp;")
        self.assertEqual(next(omabox.parse_feed(cdata))["link"], "https://example.com/p?a=1&b=2")
        japanese = '<?xml version="1.0" encoding="Shift_JIS"?><rss version="2.0"><channel><item><guid>1</guid>' \
                   '<title>\u6f6e\u898b\u306e\u8a18\u9332</title></item></channel></rss>'
        self.assertEqual(next(omabox.parse_feed(japanese.encode("shift_jis")))["title"], "\u6f6e\u898b\u306e\u8a18\u9332")
        undeclared = omabox.feed_body(japanese.split("?>", 1)[1].encode("shift_jis"),
                                      {"Content-Type": "application/rss+xml; charset=Shift_JIS"})
        self.assertEqual(next(omabox.parse_feed(undeclared))["title"], "\u6f6e\u898b\u306e\u8a18\u9332")
        latin = omabox.feed_body('<rss version="2.0"><channel><title>Fjord caf\u00e9</title></channel></rss>'.encode("latin-1"),
                                 {"Content-Type": "text/xml; charset=ISO-8859-1"})
        self.assertEqual(omabox.feed_title(latin), "Fjord caf\u00e9")
        self.assertEqual(omabox.feed_title(codecs.BOM_UTF16_LE + '<rss><channel><title>Tern</title></channel></rss>'.encode("utf-16-le")), "Tern")

    def test_tolerant_parse_stays_safe(self):
        bomb = (b'<?xml version="1.0"?><!DOCTYPE rss [<!ENTITY a "aaaaaaaaaa">'
                + b"".join(b'<!ENTITY %s "%s">' % (bytes([ord("b") + n]), (b"&" + bytes([ord("a") + n]) + b";") * 10)
                           for n in range(8))
                + b']><rss version="2.0"><channel><item><title>&i;</title></item></channel></rss>')
        try:
            titles = [entry["title"] for entry in omabox.parse_feed(bomb)]
        except omabox.ET.ParseError:
            titles = []
        self.assertLess(len("".join(titles)), 100)
        external = (b'<!DOCTYPE rss [<!ENTITY e SYSTEM "file:///etc/hostname">]>'
                    b'<rss version="2.0"><channel><item><guid>1</guid><title>&e;</title></item></channel></rss>')
        try:
            titles = [entry["title"] for entry in omabox.parse_feed(external)]
        except omabox.ET.ParseError:
            titles = []
        self.assertNotIn(Path("/etc/hostname").read_text().strip() if Path("/etc/hostname").exists() else "\0", "".join(titles))

    def test_rss(self):
        (entry,) = omabox.parse_feed(RSS_FEED)
        self.assertEqual(entry["title"], "Post & more")
        self.assertEqual(entry["guid"], "post-1")
        self.assertEqual(entry["published"], "2026-09-26T06:00:00Z")

    def test_youtube_entry_gets_thumbnail_and_description(self):
        (entry,) = omabox.parse_feed(YOUTUBE_FEED)
        self.assertEqual(entry["link"], "https://www.youtube.com/watch?v=Zq3vKe8TbWo")
        self.assertTrue(entry["html"].startswith('<img src="https://i2.ytimg.com/vi/Zq3vKe8TbWo/hqdefault.jpg">'))
        self.assertIn("<p>Think of a hand tool &lt;any&gt; at all.<br>We made one.</p><p>Discuss", entry["html"])

    def test_youtube_thumbnail_goes_through_the_image_cache(self):
        state = omabox.load_state(Path(tempfile.mkdtemp()) / "missing.json")
        directory = Path(tempfile.mkdtemp())
        fetch = lambda url, limit: jpeg(480, 360)
        omabox.merge(state, "Quarry", list(omabox.parse_feed(YOUTUBE_FEED)), "2026-09-27T08:00:00Z",
                     lambda entry: omabox.ImageFetcher(entry["link"], fetch, directory))
        (item,) = state["items"]
        self.assertIn('<img src="omabox-img:', item["html"])
        self.assertIn('width="480" height="360"', item["html"])
        self.assertTrue(item["excerpt"].startswith("Think of a hand tool <any> at all."))
        self.assertIn('<a href="https://forum.example/topic/1643100/">', item["html"])
        self.assertFalse(item["short"])

    def test_bluesky_plain_text_keeps_line_breaks_and_reads_as_a_short_post(self):
        (entry,) = omabox.parse_feed(BLUESKY_FEED)
        self.assertEqual(entry["title"], "")
        self.assertEqual(entry["published"], "2026-09-21T18:04:00Z")
        self.assertEqual(entry["html"], "If you're at the market, the bread stall is open!<br><br>It closes in 5 hours.")
        state = omabox.load_state(Path(tempfile.mkdtemp()) / "missing.json")
        omabox.merge(state, "Bluesky", [entry], "2026-09-27T08:00:00Z")
        (item,) = state["items"]
        self.assertTrue(item["short"])
        self.assertEqual(item["title"], "If you're at the market, the bread stall is open! It closes in 5 hours.")
        hearts = BLUESKY_FEED.replace(b"the bread stall", b"&lt;3 the bread stall")
        self.assertIn("<3 the bread stall is open!<br><br>It closes", next(omabox.parse_feed(hearts))["html"])
        self.assertEqual(next(omabox.parse_feed(RSS_FEED))["html"].count("<br>"), 0)

    def test_version_of(self):
        self.assertEqual(omabox.version_of("v4.0.4"), "4.0.4")
        self.assertEqual(omabox.version_of("Omarchy 3.1 is out"), "3.1")
        self.assertEqual(omabox.version_of("Slow mornings"), "")


class WebLinkTest(unittest.TestCase):
    def test_keeps_only_absolute_web_links(self):
        self.assertEqual(omabox.web_link(" https://blog.example/a "), "https://blog.example/a")
        self.assertEqual(omabox.web_link("HTTP://blog.example/a"), "HTTP://blog.example/a")
        for bad in ("file:///etc/passwd", "javascript:alert(1)", "/relative/post", "https://", "steam://run/1", None):
            self.assertEqual(omabox.web_link(bad), "", bad)

    def test_feed_post_with_a_local_link_gets_none(self):
        feed = (b'<rss version="2.0"><channel><title>t</title><item><title>a</title><link>file:///etc/passwd</link>'
                b'<guid>1</guid></item></channel></rss>')
        (entry,) = omabox.parse_feed(feed)
        self.assertEqual((entry["link"], entry["guid"]), ("", "1"))


class MergeTest(unittest.TestCase):
    def fresh(self):
        return omabox.load_state(Path(tempfile.mkdtemp()) / "missing.json")

    def test_first_fetch_leaves_only_newest_unread(self):
        state = self.fresh()
        added = omabox.merge(state, "Omarchy", list(omabox.parse_feed(ATOM_FEED)), "2026-09-26T08:00:00Z")
        # the backlog stored as read is no news: only the unread post counts
        self.assertEqual((added, len(state["items"])), (1, 2))
        unread = [i["title"] for i in state["items"] if not i["read"]]
        self.assertEqual(unread, ["v4.0.4"])
        self.assertNotIn("img", state["items"][0]["html"])
        self.assertEqual(state["items"][0]["version"], "4.0.4")

    def test_later_fetch_marks_new_items_unread_and_skips_known(self):
        state = self.fresh()
        entries = list(omabox.parse_feed(ATOM_FEED))
        omabox.merge(state, "Omarchy", entries[1:], "2026-09-02T08:00:00Z")
        state["items"][0]["read"] = True
        added = omabox.merge(state, "Omarchy", entries, "2026-09-16T08:00:00Z")
        self.assertEqual(added, 1)
        self.assertEqual({i["title"]: i["read"] for i in state["items"]}, {"v4.0.3": True, "v4.0.4": False})

    def test_trims_to_newest_per_source(self):
        state = self.fresh()
        entries = [
            {"guid": str(n), "title": f"t{n}", "link": "", "published": f"2026-01-01T00:00:{n:02d}Z", "html": ""}
            for n in range(omabox.KEEP_PER_SOURCE + 5)
        ]
        omabox.merge(state, "S", entries, "2026-09-26T08:00:00Z")
        self.assertEqual(len(state["items"]), omabox.KEEP_PER_SOURCE)
        self.assertNotIn("t0", {i["title"] for i in state["items"]})

    def test_trim_keeps_unread_and_read_later(self):
        state = self.fresh()

        def batch(start, count):
            return [{"guid": str(n), "title": f"t{n}", "link": "", "published": f"2026-01-01T00:{n // 60:02d}:{n % 60:02d}Z", "html": ""}
                    for n in range(start, start + count)]

        omabox.merge(state, "S", batch(0, 3), "2026-09-26T08:00:00Z")
        for item in state["items"]:
            item["read"] = item["title"] != "t1"
            item["later"] = item["title"] == "t0"
        omabox.merge(state, "S", batch(3, omabox.KEEP_PER_SOURCE), "2026-09-27T08:00:00Z")
        titles = {i["title"] for i in state["items"]}
        self.assertIn("t0", titles)
        self.assertIn("t1", titles)
        self.assertNotIn("t2", titles)

    def linked(self, *numbers):
        return [{"guid": f"tag:example.com,2026:{n}", "title": f"Tide report {n}", "link": f"https://example.com/{n}",
                 "published": f"2026-09-{10 + n:02d}T08:00:00Z", "html": f"<p>Report {n}</p>"} for n in numbers]

    def test_rename_keeps_posts_and_their_ids(self):
        root = Path(tempfile.mkdtemp())
        saved = {key: getattr(omabox, key) for key in ("CONFIG_PATH", "STATE_PATH")}
        self.addCleanup(lambda: [setattr(omabox, key, value) for key, value in saved.items()])
        omabox.CONFIG_PATH, omabox.STATE_PATH = root / "sources.toml", root / "items.json"
        omabox.save_sources([{"name": "Tides", "url": "https://example.com/feed", "cadence": "daily"}])
        state = omabox.load_state()
        omabox.merge(state, "Tides", self.linked(1, 2), "2026-09-13T08:00:00Z")
        for item in state["items"]:
            item.update(read=True, later=True)
        omabox.save_state(state)
        before = {item["id"] for item in state["items"]}
        with contextlib.redirect_stdout(io.StringIO()):
            omabox.main(["rename", "Tides", "Harbour tides"])
        state = omabox.load_state()
        self.assertEqual(omabox.merge(state, "Harbour tides", self.linked(1, 2, 3), "2026-09-14T08:00:00Z"), 1)
        self.assertEqual(len(state["items"]), 3)
        self.assertLessEqual(before, {item["id"] for item in state["items"]})
        self.assertEqual(sum(item.get("later", False) for item in state["items"]), 2)

    def test_posts_renamed_before_guids_were_stored_are_found_by_link(self):
        state = self.fresh()
        omabox.merge(state, "Tides", self.linked(1, 2), "2026-09-13T08:00:00Z")
        for item in state["items"]:
            del item["guid"]
            item.update(source="Harbour tides", read=True)
        self.assertEqual(omabox.merge(state, "Harbour tides", self.linked(1, 2, 3), "2026-09-14T08:00:00Z"), 1)
        self.assertEqual(len(state["items"]), 3)
        self.assertTrue(all(item["guid"].startswith("tag:example.com") for item in state["items"]))
        # an unrenamed old post is found by its id and gets its guid too
        state = self.fresh()
        omabox.merge(state, "Tides", self.linked(1), "2026-09-13T08:00:00Z")
        del state["items"][0]["guid"]
        state["items"][0]["link"] = ""
        self.assertEqual(omabox.merge(state, "Tides", self.linked(1), "2026-09-14T08:00:00Z"), 0)
        self.assertEqual([item["guid"] for item in state["items"]], ["tag:example.com,2026:1"])

    def test_a_new_source_under_a_renamed_one_s_old_name_keeps_apart(self):
        state = self.fresh()
        omabox.merge(state, "Tides", self.linked(1, 2), "2026-09-13T08:00:00Z")
        for item in state["items"]:
            item.update(source="Old tides", read=True)
        omabox.merge(state, "Tides", self.linked(1, 2), "2026-09-14T08:00:00Z")
        self.assertEqual(len(state["items"]), 4)
        self.assertEqual(len({item["id"] for item in state["items"]}), 4)
        self.assertEqual({item["source"] for item in state["items"] if item["read"]}, {"Old tides", "Tides"})
        self.assertEqual(omabox.merge(state, "Tides", self.linked(1, 2), "2026-09-15T08:00:00Z"), 0)
        self.assertEqual(omabox.merge(state, "Old tides", self.linked(1, 2), "2026-09-15T08:00:00Z"), 0)
        self.assertEqual(len(state["items"]), 4)

    def test_state_round_trip(self):
        path = Path(tempfile.mkdtemp()) / "sub" / "items.json"
        state = self.fresh()
        omabox.merge(state, "Omarchy", list(omabox.parse_feed(ATOM_FEED)), "2026-09-26T08:00:00Z")
        omabox.save_state(state, path)
        self.assertEqual(omabox.load_state(path)["items"], state["items"])


class StateFileTest(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "omabox" / "items.json"
        self.path.parent.mkdir()

    def load(self):
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            state = omabox.load_state(self.path)
        return state, errors.getvalue()

    def test_unreadable_state_is_moved_aside_not_overwritten(self):
        for broken in (b'{"items": [{"id": "a"', b"[1, 2]", b'{"items": {"a": 1}}', b'{"items": ["a"]}', b'"text"',
                       b'{"errors": []}', b"\xff\xfe{"):
            self.path.write_bytes(broken)
            state, errors = self.load()
            self.assertEqual(state["items"], [], broken)
            self.assertIn("was unreadable; moved to items.json.corrupt-", errors)
            (aside,) = self.path.parent.glob("items.json.corrupt-*")
            self.assertEqual(aside.read_bytes(), broken)
            self.assertEqual(omabox.recovered_file(state, self.path), aside.name)
            stored = json.loads(self.path.read_text())
            self.assertEqual(stored["recovered"]["file"], aside.name)
            self.assertEqual(self.load(), (stored | {"items": [], **{k: {} for k in omabox.SOURCE_STATE_KEYS}}, ""))
            aside.unlink()
            omabox.save_state(state, self.path)
            self.assertNotIn("recovered", json.loads(self.path.read_text()))

    def test_recovery_inside_the_lock_does_not_wait_on_itself(self):
        self.path.write_bytes(b"{")
        saved = omabox.STATE_PATH
        omabox.STATE_PATH = self.path
        self.addCleanup(setattr, omabox, "STATE_PATH", saved)
        done = []

        def run():
            with omabox.locked(), contextlib.redirect_stderr(io.StringIO()):
                done.append(omabox.load_state())

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        worker.join(5)
        self.assertEqual(len(done), 1)

    def test_state_is_private(self):
        self.path.parent.chmod(0o755)
        self.path.write_text('{"items": []}')
        self.path.chmod(0o644)
        omabox.save_state({"items": []}, self.path)
        self.assertEqual(self.path.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        fresh = Path(tempfile.mkdtemp()) / "new" / "items.json"
        with omabox.locked(fresh):
            omabox.save_state({"items": []}, fresh)
        self.assertEqual({p.name: p.stat().st_mode & 0o777 for p in fresh.parent.iterdir()},
                         {"items.json": 0o600, "items.lock": 0o600})
        self.assertEqual(fresh.parent.stat().st_mode & 0o777, 0o700)

    def test_save_leaves_no_temporary_file(self):
        omabox.save_state({"items": [{"id": "a", "title": "Zażółć"}]}, self.path)
        self.assertEqual([p.name for p in self.path.parent.iterdir() if p.name != "items.lock"], ["items.json"])
        self.assertEqual(omabox.load_state(self.path)["items"][0]["title"], "Zażółć")


class DoctorTest(unittest.TestCase):
    def test_fresh_install_is_not_a_problem(self):
        root = Path(tempfile.mkdtemp())
        names = ("CONFIG_PATH", "STATE_PATH", "IMAGE_DIR", "ICON_DIR", "NOTE_ARCHIVE_DIR", "OMARCHY_MENU_PATH")
        saved = {name: getattr(omabox, name) for name in names}
        self.addCleanup(lambda: [setattr(omabox, name, value) for name, value in saved.items()])
        omabox.CONFIG_PATH, omabox.STATE_PATH = root / "config" / "sources.toml", root / "state" / "items.json"
        omabox.IMAGE_DIR, omabox.ICON_DIR = root / "images", root / "icons"
        omabox.NOTE_ARCHIVE_DIR, omabox.OMARCHY_MENU_PATH = root / "notes", root / "menu.jsonc"
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.object(omabox.shutil, "which", lambda name: f"/usr/bin/{name}"):
            omabox.cmd_doctor(argparse.Namespace())
        self.assertNotIn("✗", out.getvalue())
        self.assertIn("state: none yet", out.getvalue())


class CadenceTest(unittest.TestCase):
    # Saturday 2026-09-26 09:00 local
    now = datetime(2026, 9, 26, 9, 0).astimezone()

    def iso(self, moment):
        return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def test_daily_due_once_per_day(self):
        source = {"cadence": "daily"}
        self.assertTrue(omabox.is_due(source, "", self.now))
        self.assertTrue(omabox.is_due(source, self.iso(self.now - timedelta(days=1)), self.now))
        self.assertFalse(omabox.is_due(source, self.iso(self.now - timedelta(hours=1)), self.now))

    def test_weekly_due_once_per_iso_week(self):
        source = {"cadence": "weekly"}
        monday = self.now.replace(hour=8) - timedelta(days=5)
        self.assertFalse(omabox.is_due(source, self.iso(monday), self.now))
        self.assertTrue(omabox.is_due(source, self.iso(monday - timedelta(days=1)), self.now))

    def test_weekly_on_another_day(self):
        source = {"cadence": "weekly"}
        thursday = self.now.replace(hour=8) - timedelta(days=2)
        self.assertFalse(omabox.is_due(source, self.iso(thursday), self.now, weekday=3))
        self.assertTrue(omabox.is_due(source, self.iso(thursday - timedelta(days=1)), self.now, weekday=3))
        self.assertTrue(omabox.is_due(source, self.iso(self.now - timedelta(days=1)), self.now, weekday=5))
        self.assertEqual(omabox.weekly_day({"weekly_day": "sat"}), 5)
        self.assertEqual(omabox.weekly_day({"weekly_day": "bogus"}), 0)

    def test_due_again_at_the_delivery_after_a_catch_up(self):
        # delivery at 18:00, missed yesterday, caught up at 09:00 today: 18:00 today still brings the day's posts
        source, state = {"cadence": "daily"}, {"delivery": "18:00"}
        caught_up = self.iso(self.now)
        self.assertFalse(omabox.is_due(source, caught_up, self.now.replace(hour=17, minute=59), state=state))
        self.assertTrue(omabox.is_due(source, caught_up, self.now.replace(hour=18), state=state))
        self.assertFalse(omabox.is_due(source, self.iso(self.now.replace(hour=18, minute=5)), self.now.replace(hour=23), state=state))
        # weekly on Saturday at 18:00: a catch-up Saturday morning is not that evening's delivery
        weekly = {"cadence": "weekly"}
        self.assertTrue(omabox.is_due(weekly, caught_up, self.now.replace(hour=18), weekday=5, state=state))
        self.assertFalse(omabox.is_due(weekly, caught_up, self.now.replace(hour=17), weekday=5, state=state))

    def test_paused_never_due(self):
        self.assertFalse(omabox.is_due({"cadence": "paused"}, "", self.now))


class SourcesFileTest(unittest.TestCase):
    def test_round_trip_keeps_fields_and_escapes(self):
        path = Path(tempfile.mkdtemp()) / "sources.toml"
        sources = [
            {"name": 'He said "hi"', "url": "https://a.example/feed", "cadence": "weekly"},
            {"name": "Omarchy", "url": "https://github.com/omacom/omarchy/releases.atom", "cadence": "daily",
             "version_command": "omarchy-version"},
            {"name": "Blog", "url": "https://blog.example/feed", "cadence": "daily", "full_text": True},
        ]
        omabox.save_sources(sources, path)
        self.assertEqual(omabox.load_sources(path), sources)

    def test_rejects_unknown_cadence(self):
        path = Path(tempfile.mkdtemp()) / "sources.toml"
        path.write_text('[[source]]\nname = "x"\nurl = "https://x"\ncadence = "hourly"\n')
        with self.assertRaises(ValueError):
            omabox.load_sources(path)

    def test_missing_cadence_defaults_to_daily(self):
        path = Path(tempfile.mkdtemp()) / "sources.toml"
        path.write_text('[[source]]\nname = "x"\nurl = "https://x"\n')
        self.assertEqual(omabox.load_sources(path)[0]["cadence"], "daily")

    def test_broken_toml_and_wrong_types_are_value_errors(self):
        path = Path(tempfile.mkdtemp()) / "sources.toml"
        for text in ('[[source]\nname = "x"\n', '[[source]]\nname = "x"\nurl = 1\n', 'source = "x"\n'):
            path.write_text(text)
            with self.assertRaises(ValueError):
                omabox.load_sources(path)

    def test_first_run_writes_the_default_sources(self):
        root = Path(tempfile.mkdtemp())
        saved = omabox.CONFIG_PATH
        omabox.CONFIG_PATH = root / "omabox" / "sources.toml"
        try:
            names = [source["name"] for source in omabox.load_sources()]
        finally:
            omabox.CONFIG_PATH = saved
        self.assertEqual(names, [s["name"] for s in omabox.load_sources(omabox.DEFAULT_SOURCES)])
        self.assertTrue((root / "omabox" / "sources.toml").exists())

    def test_cli_reports_errors_without_a_traceback(self):
        with self.assertRaises(SystemExit) as caught:
            omabox.main(["pause", "soon"])
        self.assertTrue(str(caught.exception.code).startswith("omabox: duration like"))


class OpmlTest(unittest.TestCase):
    SOURCES = [
        {"name": "Omarchy", "url": "https://github.com/omacom/omarchy/releases.atom", "cadence": "daily",
         "version_command": "omarchy-version"},
        {"name": 'Q&A "weekly" <digest>', "url": "https://a.example/feed?x=1&y=2", "cadence": "weekly"},
        {"name": "Rowan on X", "url": f"{omabox.RSSHUB_BASE}/twitter/user/rowanvale", "cadence": "paused"},
    ]

    def test_round_trip_into_an_empty_config(self):
        text = omabox.opml_export(self.SOURCES)
        self.assertIn('xmlns:omabox="', text)
        self.assertIn('type="rss"', text)
        sources, added, skipped = omabox.opml_import([], text.encode())
        self.assertEqual((added, skipped), (3, 0))
        expected = [{key: s[key] for key in ("name", "url", "cadence")} for s in self.SOURCES]
        self.assertEqual(sources, expected)
        path = Path(tempfile.mkdtemp()) / "sources.toml"
        omabox.save_sources(sources, path)
        self.assertEqual(omabox.load_sources(path), expected)

    def test_known_urls_are_skipped_and_names_stay_unique(self):
        existing = [{"name": "Omarchy", "url": "https://github.com/omacom/omarchy/releases.atom", "cadence": "daily"}]
        opml = b"""<opml version="1.0"><body>
          <outline text="Omarchy" xmlUrl="https://github.com/omacom/omarchy/releases.atom"/>
          <outline text="Omarchy" xmlUrl="https://omarchy.org/feed.xml"/>
          <outline text="Again" xmlUrl="https://omarchy.org/feed.xml"/>
          <outline text="Local file" xmlUrl="file:///etc/passwd"/>
        </body></opml>"""
        sources, added, skipped = omabox.opml_import(existing, opml)
        self.assertEqual((added, skipped), (1, 3))
        self.assertEqual(sources[1], {"name": "Omarchy (2)", "url": "https://omarchy.org/feed.xml", "cadence": "daily"})
        self.assertEqual(existing[1:], [])

    def test_nested_groups_are_flattened(self):
        opml = b"""<?xml version="1.0"?><opml version="2.0"><head><title>Reader</title></head><body>
          <outline text="Tech">
            <outline text="Linux">
              <outline title="Arch news" type="rss" xmlurl="https://archlinux.org/feeds/news/"/>
            </outline>
            <outline text="  Hyprland
              releases " xmlUrl="https://github.com/hyprwm/Hyprland/releases.atom"/>
          </outline>
          <outline text="" xmlUrl="https://blog.example/rss"/>
        </body></opml>"""
        sources, added, skipped = omabox.opml_import([], opml, cadence="weekly")
        self.assertEqual((added, skipped), (3, 0))
        self.assertEqual([s["name"] for s in sources], ["Arch news", "Hyprland releases", "blog.example"])
        self.assertEqual({s["cadence"] for s in sources}, {"weekly"})

    def test_not_opml(self):
        with self.assertRaises(ValueError):
            omabox.opml_import([], b"<rss/>")


class DiscoverTest(unittest.TestCase):
    def setUp(self):
        self.requested = []
        self.headers = {}
        self.pages = {}
        self.real = omabox.download

        def fake(url, headers=None):
            self.requested.append(url)
            self.headers[url] = headers
            return url, self.pages[url]

        omabox.download = fake

    def tearDown(self):
        omabox.download = self.real

    def test_site_urls_map_to_their_feeds(self):
        cases = {
            "https://www.youtube.com/channel/UCq7rWm2Lk9vBfT4xNcD8sYe":
                "https://www.youtube.com/feeds/videos.xml?channel_id=UCq7rWm2Lk9vBfT4xNcD8sYe",
            "https://youtube.com/channel/UCq7rWm2Lk9vBfT4xNcD8sYe/videos":
                "https://www.youtube.com/feeds/videos.xml?channel_id=UCq7rWm2Lk9vBfT4xNcD8sYe",
            "https://bsky.app/profile/fernwick.bsky.social": "https://bsky.app/profile/fernwick.bsky.social/rss",
            "https://bsky.app/profile/did:plc:q4m2x7c9h3k5t8w1b6n0r2pz/": "https://bsky.app/profile/did:plc:q4m2x7c9h3k5t8w1b6n0r2pz/rss",
            "https://news.ycombinator.com": "https://hnrss.org/frontpage",
            "https://news.ycombinator.com/": "https://hnrss.org/frontpage",
            "https://news.ycombinator.com/news?p=2": "https://hnrss.org/frontpage",
            "https://news.ycombinator.com/show": "https://hnrss.org/show",
            "https://www.reddit.com/r/archlinux/": "https://www.reddit.com/r/archlinux/.rss",
            "https://old.reddit.com/r/unixporn": "https://www.reddit.com/r/unixporn/.rss",
            "https://reddit.com/u/fernhollow": "https://www.reddit.com/user/fernhollow/.rss",
        }
        for url, feed in cases.items():
            self.assertEqual(omabox.site_feed(url), feed, url)
        for url in ("https://www.youtube.com/@QuarryBench", "https://bsky.app/profile/fernwick.bsky.social/rss",
                    "https://news.ycombinator.com/item?id=1", "https://hnrss.org/frontpage?points=200",
                    "https://www.reddit.com/r/archlinux/.rss", "https://www.reddit.com/r/archlinux/comments/abc/x/",
                    "https://mastodon.social/@tidepool"):
            self.assertIsNone(omabox.site_feed(url), url)

    def test_hnrss_query_passes_through(self):
        self.pages["https://hnrss.org/frontpage?points=200"] = RSS_FEED
        found = omabox.discover("hnrss.org/frontpage?points=200")
        self.assertEqual(found["url"], "https://hnrss.org/frontpage?points=200")
        self.assertEqual(self.requested, ["https://hnrss.org/frontpage?points=200"])

    def test_youtube_handle_page_sends_consent_cookie(self):
        feed = "https://www.youtube.com/feeds/videos.xml?channel_id=UCq7rWm2Lk9vBfT4xNcD8sYe"
        self.pages["https://www.youtube.com/@QuarryBench"] = (
            f'<html><head><link rel="alternate" type="application/rss+xml" title="RSS" href="{feed}"></head></html>').encode()
        self.pages[feed] = YOUTUBE_FEED
        found = omabox.discover("https://www.youtube.com/@QuarryBench")
        self.assertEqual(found["url"], feed)
        self.assertEqual(found["title"], "Quarry Bench")
        self.assertIn("SOCS=", self.headers["https://www.youtube.com/@QuarryBench"]["Cookie"])

    def test_latest_of_untitled_posts_shows_their_text(self):
        self.pages["https://bsky.app/profile/fernwick.bsky.social/rss"] = BLUESKY_FEED
        found = omabox.discover("https://bsky.app/profile/fernwick.bsky.social")
        self.assertEqual(found["latest"], {"title": "If you're at the market, the bread stall is open! It closes in 5 hours.",
                                           "published": "2026-09-21T18:04:00Z"})

    def test_mastodon_profile_links_its_feed(self):
        self.pages["https://mastodon.social/@tidepool"] = (
            b'<link href="https://mastodon.social/@tidepool.rss" rel="alternate" type="application/rss+xml">'
            b'<link href="https://mastodon.social/users/tidepool" rel="alternate" type="application/activity+json">')
        self.pages["https://mastodon.social/@tidepool.rss"] = RSS_FEED
        self.assertEqual(omabox.discover("https://mastodon.social/@tidepool")["url"], "https://mastodon.social/@tidepool.rss")
        self.assertIsNone(self.headers["https://mastodon.social/@tidepool"])

    def test_github_repo_becomes_releases_feed(self):
        self.pages["https://github.com/hyprwm/Hyprland/releases.atom"] = ATOM_FEED
        found = omabox.discover("github.com/hyprwm/Hyprland")
        self.assertEqual(found["url"], "https://github.com/hyprwm/Hyprland/releases.atom")
        self.assertEqual(found["title"], "Hyprland releases")
        self.assertEqual(found["latest"]["title"], "v4.0.4")

    def test_page_with_alternate_link(self):
        self.pages["https://blog.example/"] = b'<html><head><link rel="alternate" type="application/rss+xml" href="/rss"></head></html>'
        self.pages["https://blog.example/rss"] = RSS_FEED
        found = omabox.discover("https://blog.example/")
        self.assertEqual(found["url"], "https://blog.example/rss")
        self.assertEqual(found["count"], 1)

    def test_rsshub_x_route_starts_rsshub(self):
        started = []
        real_session = omabox.rsshub_session
        omabox.rsshub_session = lambda needed=True: started.append(needed) or contextlib.nullcontext()
        self.addCleanup(setattr, omabox, "rsshub_session", real_session)
        route = f"{omabox.RSSHUB_BASE}/twitter/user/rowanvale/includeRts=false"
        self.pages[route] = RSS_FEED
        found = omabox.discover(route)
        self.assertEqual(started, [True])
        self.assertEqual((found["url"], found["title"]), (route, "@rowanvale on X"))

    def test_page_without_feed(self):
        self.pages["https://plain.example/"] = b"<html><body>hi</body></html>"
        with self.assertRaises(ValueError):
            omabox.discover("https://plain.example/")


def png(width, height):
    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + width.to_bytes(4, "big") + height.to_bytes(4, "big") + b"\x08\x06\x00\x00\x00"


def jpeg(width, height):
    sof = b"\xff\xc0\x00\x11\x08" + height.to_bytes(2, "big") + width.to_bytes(2, "big") + b"\x03" + b"\x00" * 9
    return b"\xff\xd8" + b"\xff\xe0\x00\x10" + b"JFIF\x00" + b"\x00" * 9 + sof


class ImageTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp()) / "images"
        self.served = {}
        self.calls = []

    def fetch(self, url, limit):
        self.calls.append(url)
        if url not in self.served:
            raise OSError("404")
        return self.served[url]

    def fetcher(self, base="https://blog.example/post"):
        return omabox.ImageFetcher(base, self.fetch, self.dir)

    def test_image_info(self):
        self.assertEqual(omabox.image_info(png(640, 480)), ("png", 640, 480))
        self.assertEqual(omabox.image_info(jpeg(800, 600)), ("jpg", 800, 600))
        self.assertEqual(omabox.image_info(b"GIF89a" + (320).to_bytes(2, "little") + (200).to_bytes(2, "little")), ("gif", 320, 200))
        self.assertIsNone(omabox.image_info(b"<svg xmlns='http://www.w3.org/2000/svg'/>"))

    def test_downloads_and_references_local_copy(self):
        self.served["https://blog.example/a.png"] = png(640, 480)
        body, _ = omabox.sanitize('<p>Look <img src="/a.png"></p>', self.fetcher())
        (name,) = omabox.IMAGE_REF_RE.findall(body)
        self.assertIn(f'<img src="omabox-img:{name}" width="640" height="480">', body)
        self.assertEqual((self.dir / name).read_bytes(), png(640, 480))

    @unittest.skipUnless(omabox.shutil.which("magick"), "needs ImageMagick")
    def test_wide_pictures_are_cached_scaled_down(self):
        for kind in ("jpg", "png", "webp"):
            photo = subprocess.run(["magick", "-size", "2000x1500", "gradient:navy-orange", f"{kind}:-"], capture_output=True,
                                   check=True).stdout
            self.served[f"https://blog.example/{kind}"] = photo
            body, _ = omabox.sanitize(f'<img src="/{kind}">', self.fetcher())
            self.assertIn('width="1600" height="1200"', body, kind)
            (name,) = omabox.IMAGE_REF_RE.findall(body)
            self.assertEqual(omabox.image_info((self.dir / name).read_bytes()), (kind, 1600, 1200))
        self.served["https://blog.example/narrow.png"] = png(1200, 900)
        body, _ = omabox.sanitize('<img src="/narrow.png">', self.fetcher())
        self.assertIn('width="1200" height="900"', body)

    def test_pictures_stay_as_they_are_without_a_working_magick(self):
        wide = jpeg(4000, 3000)
        self.served["https://blog.example/w.jpg"] = wide
        with mock.patch.object(omabox.shutil, "which", lambda name: None):
            body, _ = omabox.sanitize('<img src="/w.jpg">', self.fetcher())
        self.assertIn('width="4000" height="3000"', body)
        for failure in (subprocess.TimeoutExpired("magick", 20), OSError("gone")):
            self.dir = Path(tempfile.mkdtemp())
            with mock.patch.object(omabox.subprocess, "run", side_effect=failure), \
                    mock.patch.object(omabox.shutil, "which", lambda name: "/usr/bin/magick"):
                body, _ = omabox.sanitize('<img src="/w.jpg">', self.fetcher())
            self.assertIn('width="4000" height="3000"', body)
            self.assertEqual(next(self.dir.iterdir()).read_bytes(), wide)
        gif = b"GIF89a" + (4000).to_bytes(2, "little") + (3000).to_bytes(2, "little") + b"\x00" * 8
        self.served["https://blog.example/a.gif"] = gif
        with mock.patch.object(omabox.subprocess, "run") as run:
            body, _ = omabox.sanitize('<img src="/a.gif">', self.fetcher())
        run.assert_not_called()
        self.assertIn('width="4000"', body)

    def test_skips_tracking_pixels_without_download_when_declared(self):
        body, _ = omabox.sanitize('<img src="https://t.example/p.gif" width="1" height="1">', self.fetcher())
        self.assertEqual(body, "")
        self.assertEqual(self.calls, [])

    def test_skips_tracking_pixels_by_real_size(self):
        self.served["https://t.example/p.png"] = png(1, 1)
        body, _ = omabox.sanitize('<img src="https://t.example/p.png">', self.fetcher())
        self.assertEqual(body, "")

    def test_failed_or_non_image_becomes_link(self):
        self.served["https://blog.example/x.svg"] = b"<svg/>"
        body, _ = omabox.sanitize('<img src="https://blog.example/x.svg"><img src="https://blog.example/gone.png">', self.fetcher())
        self.assertEqual(body.count("▢ image"), 2)
        self.assertNotIn("<img", body)

    def test_caps_images_per_item(self):
        tags = ""
        for n in range(omabox.MAX_IMAGES_PER_ITEM + 2):
            self.served[f"https://blog.example/{n}.png"] = png(100 + n, 100)
            tags += f'<img src="https://blog.example/{n}.png">'
        body, _ = omabox.sanitize(tags, self.fetcher())
        self.assertEqual(body.count("<img"), omabox.MAX_IMAGES_PER_ITEM)
        self.assertEqual(body.count("▢ image"), 2)

    def test_without_hook_images_are_dropped(self):
        body, _ = omabox.sanitize('<img src="https://blog.example/a.png">')
        self.assertEqual(body, "")

    X_VIDEO = ('Cameras<br><video width="1280" height="720" src="https://video.twimg.com/v/a.mp4?tag=29&amp;x=1" '
               'controls="controls" poster="https://pbs.twimg.com/thumb/a.jpg"></video>')

    def test_video_becomes_its_poster_linked_to_the_file(self):
        self.served["https://pbs.twimg.com/thumb/a.jpg"] = jpeg(1280, 720)
        body, text = omabox.sanitize(self.X_VIDEO, self.fetcher())
        (name,) = omabox.IMAGE_REF_RE.findall(body)
        self.assertEqual(body, 'Cameras<br><p><a href="https://video.twimg.com/v/a.mp4?tag=29&amp;x=1">'
                               f'<img src="omabox-poster:{name}" width="1280" height="720"></a></p>')
        self.assertEqual(text, "Cameras")
        self.assertTrue((self.dir / name).is_file())

    def test_video_source_child_resolved_and_fallback_text_dropped(self):
        self.served["https://blog.example/p.png"] = png(640, 360)
        body, text = omabox.sanitize('<video poster="p.png" controls><source src="clip.webm" type="video/webm">'
                                     '<source src="clip.mp4">Your browser cannot play <b>this</b>.</video><p>After</p>',
                                     self.fetcher())
        self.assertIn('<a href="https://blog.example/clip.webm"><img src="omabox-poster:', body)
        self.assertNotIn("browser", body + text)
        self.assertTrue(body.endswith("<p>After</p>"))

    def test_video_without_a_poster_to_show_becomes_a_link(self):
        self.served["https://cdn.example/p.jpg"] = jpeg(64, 36)
        body, _ = omabox.sanitize('<video src="https://cdn.example/a.mp4"></video>'
                                  '<video src="https://cdn.example/b.mp4" poster="https://cdn.example/gone.jpg"/>'
                                  '<video src="http://cdn.example/c.mp4" poster="https://cdn.example/p.jpg"/>'
                                  '<video poster="https://cdn.example/x.jpg"></video>', self.fetcher())
        self.assertEqual(body, '<p><a href="https://cdn.example/a.mp4">▶ video</a></p>'
                               '<p><a href="https://cdn.example/b.mp4">▶ video</a></p>'
                               '<p><a href="http://cdn.example/c.mp4">▶ video</a></p>')

    def test_without_hook_videos_are_dropped(self):
        self.assertEqual(omabox.sanitize(self.X_VIDEO)[0], "Cameras<br>")
        self.assertEqual(omabox.sanitize(self.X_VIDEO, lambda attrs: "")[0], "Cameras<br>")

    def test_comment_and_quote_posters_get_depth_and_stay_picture_paragraphs(self):
        self.served["https://pbs.twimg.com/thumb/a.jpg"] = jpeg(1280, 720)
        reply = {"handle": "fan", "name": "Fan", "id": "7", "published": "", "avatar": "", "html": self.X_VIDEO}
        comment = omabox.comment_markup(reply, "rowanvale", self.fetcher(), {}, 2)
        self.assertRegex(comment, r'<p><a href="[^"]+"><img src="omabox-poster:\w+\.jpg" width="1280" height="720" depth="2">')
        quote = omabox.quote_markup({"name": "Q", "handle": "q", "link": "", "html": self.X_VIDEO}, self.fetcher())
        self.assertIn('height="720" depth="0">', quote)

    def test_prune_keeps_posters(self):
        self.served["https://pbs.twimg.com/thumb/a.jpg"] = jpeg(1280, 720)
        body, _ = omabox.sanitize(self.X_VIDEO, self.fetcher())
        (self.dir / "0123456789abcdef0123.png").write_bytes(png(9, 9))
        later = time.time() + omabox.PRUNE_GRACE_SECONDS + 1
        omabox.prune_images({"items": [{"html": body}]}, self.dir, later)
        self.assertEqual([path.name for path in self.dir.iterdir()], omabox.IMAGE_REF_RE.findall(body))

    def test_prune_spares_pictures_written_moments_ago(self):
        (self.dir).mkdir(parents=True)
        fresh, old = self.dir / "0123456789abcdef0123.png", self.dir / "abcdef0123456789abcd.png"
        fresh.write_bytes(png(9, 9))
        old.write_bytes(png(9, 9))
        stale = time.time() - omabox.PRUNE_GRACE_SECONDS - 60
        omabox.os.utime(old, (stale, stale))
        omabox.prune_images({"items": []}, self.dir)
        self.assertEqual([path.name for path in self.dir.iterdir()], [fresh.name])
        # a cache hit refreshes the file, so a post about to reference it again keeps it
        omabox.os.utime(fresh, (stale, stale))
        self.served["https://blog.example/fresh.png"] = png(9, 9)
        stem = omabox.hashlib.sha1(b"https://blog.example/fresh.png").hexdigest()[:20]
        fresh.rename(self.dir / f"{stem}.png")
        omabox.sanitize('<img src="/fresh.png">', self.fetcher())
        omabox.prune_images({"items": []}, self.dir)
        self.assertEqual([path.name for path in self.dir.iterdir()], [f"{stem}.png"])

    def test_merge_rebuilds_items_from_older_format(self):
        state = omabox.load_state(Path(tempfile.mkdtemp()) / "missing.json")
        entries = list(omabox.parse_feed(ATOM_FEED))
        omabox.merge(state, "Omarchy", entries, "2026-09-26T08:00:00Z")
        for item in state["items"]:
            item.pop("media")
            item["html"] = "old"
            item["read"] = True
        added = omabox.merge(state, "Omarchy", entries, "2026-09-27T08:00:00Z")
        self.assertEqual(added, 0)
        self.assertTrue(all(i["html"] != "old" and i["read"] for i in state["items"]))


class IconTest(unittest.TestCase):
    def test_known_hosts_get_glyphs(self):
        self.assertEqual(omabox.glyph_for("https://github.com/omacom/omarchy/releases.atom"), chr(0xF02A4))
        self.assertEqual(omabox.glyph_for("http://localhost:1200/twitter/user/rowanvale"), chr(0xF0544))
        self.assertEqual(omabox.glyph_for("https://world.hey.com/rowanvale/feed.atom"), "")
        self.assertEqual(omabox.glyph_for("https://www.youtube.com/feeds/videos.xml?channel_id=UC1"), chr(0xF05C3))
        self.assertEqual(omabox.glyph_for("https://bsky.app/profile/fernwick.bsky.social/rss"), chr(0xF1589))
        self.assertEqual(omabox.glyph_for("https://hnrss.org/frontpage?points=200"), chr(0xF0B20))
        self.assertEqual(omabox.glyph_for("https://www.reddit.com/r/archlinux/.rss"), chr(0xF044D))
        self.assertEqual(omabox.glyph_for("https://fosstodon.org/@someone.rss"), chr(0xF0AD1))
        self.assertEqual(omabox.glyph_for("https://blog.example/@home.xml"), "")

    def test_favicon_from_page_link_then_rss_fallback(self):
        directory = Path(tempfile.mkdtemp())
        served = {
            "https://world.hey.com/rowanvale": b'<link rel="icon" href="/fav.png"><link rel="icon" href="/logo.svg">',
            "https://world.hey.com/fav.png": png(32, 32),
        }

        def fetch(url, limit):
            if url not in served:
                raise OSError("404")
            return served[url]

        feed = b'<feed xmlns="http://www.w3.org/2005/Atom"><link rel="alternate" href="https://world.hey.com/rowanvale"/></feed>'
        state = {"icons": {}}
        source = {"name": "Rowan", "url": "https://world.hey.com/rowanvale/feed.atom"}
        omabox.ensure_icon(state, source, feed, fetch, directory)
        self.assertTrue(state["icons"]["Rowan"]["favicon"].endswith(".png"))
        self.assertTrue(Path(state["icons"]["Rowan"]["favicon"]).exists())

        served.clear()
        state = {"icons": {}}
        omabox.ensure_icon(state, {"name": "X", "url": "https://nothing.example/feed"}, b"", fetch, directory)
        self.assertEqual(state["icons"]["X"], {"glyph": chr(0xF046B)})

    def test_override_wins(self):
        state = {"icons": {}}
        omabox.ensure_icon(state, {"name": "A", "url": "https://github.com/a/b/releases.atom", "icon": "*"})
        self.assertEqual(state["icons"]["A"], {"glyph": "*"})


class PublicHostTest(unittest.TestCase):
    def test_refuses_local_and_private_targets(self):
        for url in ("http://127.0.0.1/x.png", "http://localhost:8080/", "http://192.168.1.1/a.png",
                    "http://10.0.0.5/", "http://169.254.169.254/latest", "http://[::1]/", "file:///etc/passwd",
                    "http://[::ffff:10.0.0.5]/"):
            self.assertFalse(omabox.public_host(url), url)

    def test_public_address(self):
        shared = ipaddress.ip_network((0x64400000, 10))  # RFC 6598 shared address space
        for address in (str(shared[1]), str(shared[shared.num_addresses // 2]), str(shared[-2]), "224.0.0.1", "ff02::1",
                        "fd00::1", "fe80::1%eth0", "0.0.0.0", "192.0.2.1"):
            self.assertFalse(omabox.public_address(address), address)
        for address in ("93.184.216.34", "2606:4700::1111"):
            self.assertTrue(omabox.public_address(address), address)

    def test_nat64_and_6to4_follow_the_embedded_ipv4(self):
        nat64 = int(ipaddress.ip_address("64:ff9b::"))
        for inner in ("127.0.0.1", "10.0.0.5", "169.254.169.254", "192.168.1.1"):
            embedded = int(ipaddress.ip_address(inner))
            self.assertFalse(omabox.public_address(str(ipaddress.IPv6Address(nat64 + embedded))), inner)
            self.assertFalse(omabox.public_address(str(ipaddress.IPv6Address((0x2002 << 112) + (embedded << 80) + 1))), inner)
        self.assertTrue(omabox.public_address(str(ipaddress.IPv6Address(nat64 + int(ipaddress.ip_address("93.184.216.34"))))))
        self.assertFalse(omabox.public_address("64:ff9b:1::5db8:d822"))

    def test_download_limited_refuses_before_connecting(self):
        with self.assertRaises(ValueError):
            omabox.download_limited("http://127.0.0.1:9/x.png", 100)

    def test_rebinding_after_the_check_is_refused(self):
        answers = iter(["93.184.216.34", "127.0.0.1"])

        def resolve(host, port, *args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (next(answers), port or 0))]

        with mock.patch.object(omabox.socket, "getaddrinfo", resolve), mock.patch.object(omabox.socket, "socket") as dial:
            with self.assertRaisesRegex(OSError, "non-public address refused"):
                omabox.download_public("http://rebind.example/x.png", 100)
        dial.assert_not_called()

    def test_public_download_goes_through_the_checked_connection(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.end_headers()
                self.wfile.write(b"png")

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        with mock.patch.object(omabox, "public_address", lambda address: True):
            self.assertEqual(omabox.download_limited(f"http://127.0.0.1:{server.server_port}/x.png", 100), b"png")


RELEASE_HTML = (
    '<p>This release brings our kernel.</p>'
    '<p>Download: <a href="https://iso.omarchy.org/x.iso">iso</a><br>SHA256: abc</p>'
    '<h2>Improvements</h2><ul><li>New kernel by <a href="https://github.com/kw">@kw</a></li></ul>'
    '<h2>Fixes</h2><ul>'
    '<li>Fix webcam by <a href="https://github.com/a">@a</a> and <a href="https://github.com/b">@b</a> '
    'in <a href="https://github.com/o/r/pull/1">#1</a></li>'
    '<li>Fix audio<ul><li>nested detail</li></ul></li>'
    '</ul>'
    '<h2>New Contributors</h2><ul><li><a href="https://github.com/c">@c</a> made their first contribution</li></ul>'
    '<p>Full Changelog: <a href="https://github.com/o/r/compare/a...b">a...b</a></p>'
)


class StructureTest(unittest.TestCase):
    def shaped(self):
        body, text = omabox.sanitize(RELEASE_HTML)
        return omabox.structure(body, text)

    def test_summary_counts_top_level_items_per_heading(self):
        _, summary, _ = self.shaped()
        self.assertEqual(summary, "Improvements 1  ·  Fixes 2")

    def test_credits_are_wrapped(self):
        body, _, _ = self.shaped()
        self.assertIn('New kernel<span class="credit"> by <a href="https://github.com/kw">@kw</a></span></li>', body)
        self.assertIn('<span class="credit"> by <a href="https://github.com/a">@a</a> and <a href="https://github.com/b">@b</a> '
                      'in <a href="https://github.com/o/r/pull/1">#1</a></span></li>', body)

    def test_boilerplate_moves_last_and_dims(self):
        body, _, _ = self.shaped()
        blocks = omabox.top_level_blocks(body)
        self.assertTrue(blocks[0].startswith("<p>This release"))
        self.assertTrue(blocks[-4].startswith('<p class="meta">Download:'))
        self.assertTrue(blocks[-3].startswith('<p class="h meta">New Contributors'))
        self.assertTrue(blocks[-2].startswith('<div class="meta"><ul><li>'))
        self.assertTrue(blocks[-1].startswith('<p class="meta">Full Changelog'))

    def test_plain_blog_post_has_no_summary(self):
        body, text = omabox.sanitize("<div>" + "word " * 700 + "</div>")
        shaped, summary, minutes = omabox.structure(body, text)
        self.assertEqual(summary, "")
        self.assertEqual(minutes, 3)
        self.assertEqual(shaped, body)

    def test_minor_headings_become_subheads(self):
        body, _ = omabox.sanitize("<h2>Section</h2><h3>Detail</h3><h5>Tiny</h5>")
        self.assertEqual(body, '<p class="h">Section</p><p class="sub">Detail</p><p class="sub">Tiny</p>')

    def test_top_level_blocks_keep_loose_text(self):
        self.assertEqual(omabox.top_level_blocks("hi<br><p>a<b>b</b></p>tail"), ["hi<br>", "<p>a<b>b</b></p>", "tail"])

    def test_spaces_between_inline_elements_survive(self):
        body = '<a href="https://x.com/ada">@ada</a> <a href="https://x.com/bo">@bo</a> hi<p>next</p> <b>x</b> <i>y</i>'
        self.assertEqual(omabox.top_level_blocks(body),
                         ['<a href="https://x.com/ada">@ada</a> <a href="https://x.com/bo">@bo</a> hi', "<p>next</p>",
                          " <b>x</b> <i>y</i>"])
        self.assertEqual(omabox.structure(body, "")[0], body)
        self.assertEqual(omabox.reply_paragraphs(body, "said"),
                         '<p class="said"><a href="https://x.com/ada">@ada</a> <a href="https://x.com/bo">@bo</a> hi</p>'
                         '<p class="said">next</p><p class="said"><b>x</b> <i>y</i></p>')


class CalmTest(unittest.TestCase):
    def test_parse_duration(self):
        self.assertEqual(omabox.parse_duration("3d"), timedelta(days=3))
        self.assertEqual(omabox.parse_duration("12h"), timedelta(hours=12))
        self.assertEqual(omabox.parse_duration("90m"), timedelta(minutes=90))
        self.assertEqual(omabox.parse_duration("2w"), timedelta(weeks=2))
        with self.assertRaises(ValueError):
            omabox.parse_duration("soon")

    def test_next_morning_is_tomorrow_at_eight_local(self):
        now = datetime(2026, 9, 26, 23, 30).astimezone()
        morning = datetime.fromisoformat(omabox.next_morning(now)).astimezone(now.tzinfo)
        self.assertEqual((morning.day, morning.hour, morning.minute), (27, 8, 0))

    def test_paused(self):
        now = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
        self.assertTrue(omabox.paused({"paused_until": "2026-09-27T12:00:00Z"}, now))
        self.assertFalse(omabox.paused({"paused_until": "2026-09-25T12:00:00Z"}, now))
        self.assertFalse(omabox.paused({}, now))


def entry(guid, title, html="", published="2026-09-26T08:00:00Z"):
    return {"guid": guid, "title": title, "link": "", "published": published, "html": html}


class MuteTest(unittest.TestCase):
    def test_plain_words_and_regexes_ignore_case(self):
        word = omabox.mute_matcher("  Giveaway ")
        self.assertTrue(word("Huge GIVEAWAY today"))
        self.assertFalse(word("give away"))
        regex = omabox.mute_matcher(r"/\bRT\b|sponsor(ed)?/")
        self.assertTrue(regex("rt this"))
        self.assertTrue(regex("A Sponsored post"))
        self.assertFalse(regex("start here"))
        self.assertTrue(omabox.mute_matcher("/")("a/b"))
        self.assertTrue(omabox.mute_matcher("/a{1,3}b/")("xaab"))

    def test_bad_rules_are_refused_with_a_reason(self):
        with self.assertRaisesRegex(ValueError, "not a valid regex"):
            omabox.mute_matcher("/x(/")
        for rule in ("  ", " // "):
            with self.assertRaisesRegex(ValueError, "empty"):
                omabox.mute_matcher(rule)

    def test_mutes_all_needs_every_stored_post_of_the_source(self):
        state = {"items": [{"source": "S", "title": "One", "html": ""}, {"source": "S", "title": "Two", "html": ""},
                           {"source": "T", "title": "zzz", "html": ""}]}
        self.assertEqual(omabox.mutes_all(state, "S", omabox.mute_filter(["/.+/"])), 2)
        self.assertEqual(omabox.mutes_all(state, "S", omabox.mute_filter(["/w/"])), 0)
        self.assertEqual(omabox.mutes_all(state, "T", omabox.mute_filter(["zzz"])), 0)

    def test_filter_skips_invalid_rules_and_reports_them(self):
        problems = []
        muted = omabox.mute_filter(["/x(/", "rust"], problems.append)
        self.assertTrue(muted("Rewritten in Rust", ""))
        self.assertTrue(muted("", "now in rust"))
        self.assertFalse(muted("Go", "go"))
        self.assertEqual(len(problems), 1)
        self.assertIsNone(omabox.mute_filter(["/x(/"], problems.append))
        self.assertIsNone(omabox.mute_filter([]))

    def test_merge_leaves_muted_entries_out(self):
        state = omabox.load_state(Path(tempfile.mkdtemp()) / "missing.json")
        entries = [entry("1", "Giveaway time", published="2026-09-26T10:00:00Z"),
                   entry("2", "Release notes", "<p>a giveaway inside</p>", "2026-09-26T09:00:00Z"),
                   entry("3", "Plain post", "<p>text</p>", "2026-09-26T08:00:00Z"),
                   entry("4", "Older post", "<p>text</p>", "2026-09-25T08:00:00Z")]
        added = omabox.merge(state, "S", entries, "2026-09-27T08:00:00Z", muted=omabox.mute_filter(["giveaway"]))
        self.assertEqual(added, 1)
        self.assertEqual({i["title"]: i["read"] for i in state["items"]}, {"Plain post": False, "Older post": True})

    def test_invalid_rule_does_not_stop_a_fetch(self):
        state = omabox.load_state(Path(tempfile.mkdtemp()) / "missing.json")
        source = {"name": "S", "url": "https://a.example/feed", "icon": "*", "mute": ["/x(/", "hello"]}
        errors = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(errors):
            added = omabox.fetch_source(state, source, "2026-09-27T08:00:00Z", get=lambda url, cached: (RSS_FEED, {}))
        self.assertEqual((added, state["items"], state["errors"]), (0, [], {}))
        self.assertIn("not a valid regex", errors.getvalue())

    def test_drop_muted_keeps_read_later_and_other_sources(self):
        state = {"items": [
            {"id": "a", "source": "S", "title": "Sponsored", "html": ""},
            {"id": "b", "source": "S", "title": "Post", "html": "<p>sponsored by</p>"},
            {"id": "c", "source": "S", "title": "Sponsored", "html": "", "later": True},
            {"id": "d", "source": "T", "title": "Sponsored", "html": ""},
            {"id": "e", "source": "S", "title": "Fine", "html": "<p>ok</p>"},
        ]}
        self.assertEqual(omabox.drop_muted(state, "S", omabox.mute_filter(["sponsored"])), 2)
        self.assertEqual([i["id"] for i in state["items"]], ["c", "d", "e"])

    def test_sources_file_round_trips_rules(self):
        path = Path(tempfile.mkdtemp()) / "sources.toml"
        sources = [{"name": "S", "url": "https://a.example/feed", "cadence": "daily",
                    "mute": [r"/a{1,3}\d, \/x/", 'say "hi"', "zażółć", "a, b"]}]
        omabox.save_sources(sources, path)
        self.assertEqual(omabox.load_sources(path), sources)
        self.assertIn("mute", omabox.SOURCES_HEADER)
        omabox.save_sources([{**sources[0], "mute": []}], path)
        self.assertNotIn("mute =", path.read_text())

    def test_mute_must_be_a_list_of_strings(self):
        path = Path(tempfile.mkdtemp()) / "sources.toml"
        for value in ('"giveaway"', "[1]"):
            path.write_text(f'[[source]]\nname = "x"\nurl = "https://x"\nmute = {value}\n')
            with self.assertRaisesRegex(ValueError, "mute must be a list of strings"):
                omabox.load_sources(path)


class XRouteTest(unittest.TestCase):
    ROUTE = f"{omabox.RSSHUB_BASE}/twitter/user/rowanvale"

    def test_rsshub_defaults_hide_replies_and_keep_reposts(self):
        self.assertEqual(omabox.x_hidden(self.ROUTE), {"reposts": False, "replies": True})
        self.assertIsNone(omabox.x_route("https://x.com/rowanvale"))
        self.assertIsNone(omabox.x_route(f"{omabox.RSSHUB_BASE}/github/repos/rowanvale"))

    def test_route_params_switch_reposts_and_replies(self):
        hidden = omabox.x_route_url(self.ROUTE, reposts=True)
        self.assertEqual(hidden, self.ROUTE + "/includeRts=false")
        self.assertEqual(omabox.x_hidden(hidden), {"reposts": True, "replies": True})
        both = omabox.x_route_url(hidden, replies=False)
        self.assertEqual(omabox.x_hidden(both), {"reposts": True, "replies": False})
        self.assertEqual(omabox.x_route_url(both, reposts=False, replies=True), self.ROUTE)

    def test_named_params_and_extra_params(self):
        self.assertEqual(omabox.x_hidden(self.ROUTE + "/exclude_rts"), {"reposts": True, "replies": True})
        self.assertEqual(omabox.x_hidden(self.ROUTE + "/include_replies"), {"reposts": False, "replies": False})
        self.assertEqual(omabox.x_route_url(self.ROUTE + "/count=40", reposts=True), self.ROUTE + "/count=40&includeRts=false")


class MuteCommandTest(unittest.TestCase):
    X_URL = f"{omabox.RSSHUB_BASE}/twitter/user/rowanvale"

    def setUp(self):
        root = Path(tempfile.mkdtemp())
        self.saved = {key: getattr(omabox, key) for key in ("CONFIG_PATH", "STATE_PATH", "IMAGE_DIR")}
        omabox.CONFIG_PATH, omabox.STATE_PATH, omabox.IMAGE_DIR = root / "sources.toml", root / "items.json", root / "images"
        omabox.save_sources([{"name": "Blog", "url": "https://a.example/feed", "cadence": "daily"},
                             {"name": "Rowan", "url": self.X_URL, "cadence": "daily"}])
        state = omabox.load_state()
        day = "2026-09-26T08:00:00Z"
        state["items"] = [
            {"id": "1", "source": "Blog", "title": "Sponsored: tools", "html": "", "published": day, "read": False},
            {"id": "2", "source": "Blog", "title": "Sponsored too", "html": "", "published": day, "read": True, "later": True},
            {"id": "3", "source": "Blog", "title": "A post", "html": "<p>-x- inside</p>", "published": day, "read": False},
        ]
        state["http"] = {"Blog": {"etag": '"1"'}, "Rowan": {"etag": '"2"'}}
        omabox.save_state(state)

    def tearDown(self):
        for key, value in self.saved.items():
            setattr(omabox, key, value)

    def run_cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            omabox.main(list(argv))
        return out.getvalue()

    def blog(self):
        return next(s for s in omabox.load_sources() if s["name"] == "Blog")

    def test_add_list_and_remove_rules(self):
        out = self.run_cli("mute", "Blog", "--", "sponsored", "-x-", "/a{1,3}, b/")
        self.assertIn("removed 2 stored posts", out)
        self.assertEqual(self.blog()["mute"], ["sponsored", "-x-", "/a{1,3}, b/"])
        self.assertEqual([i["id"] for i in omabox.load_state()["items"]], ["2"])
        self.assertIn("already muted: sponsored", self.run_cli("mute", "Blog", "sponsored"))
        self.assertEqual(self.run_cli("mute", "Blog"), "sponsored\n-x-\n/a{1,3}, b/\n")
        self.run_cli("unmute", "Blog", "--", "-x-", "sponsored")
        self.assertEqual(self.blog()["mute"], ["/a{1,3}, b/"])
        self.assertNotIn("Blog", omabox.load_state()["http"])

    def test_bad_input_changes_nothing(self):
        for argv in (("mute", "Blog", "/x(/"), ("unmute", "Blog", "nope"), ("mute", "Blog", "--reposts"),
                     ("unmute", "Blog"), ("mute", "Nope", "x"), ("mute", "Blog", "ok", "/a*/")):
            with self.assertRaises(SystemExit) as caught, contextlib.redirect_stdout(io.StringIO()):
                omabox.main(list(argv))
            self.assertIsInstance(caught.exception.code, str, argv)
        self.assertNotIn("mute", self.blog())

    def test_x_reposts_go_through_the_route(self):
        self.assertIn("X: reposts hidden, replies hidden", self.run_cli("mute", "Rowan", "--reposts"))
        rowanvale = next(s for s in omabox.load_sources() if s["name"] == "Rowan")
        self.assertEqual(rowanvale["url"], self.X_URL + "/includeRts=false")
        self.assertNotIn("Rowan", omabox.load_state()["http"])
        self.assertIn("X: reposts shown, replies shown", self.run_cli("unmute", "Rowan", "--reposts", "--replies"))
        self.assertIn("X: reposts shown, replies shown", self.run_cli("mute", "Rowan"))
        (row,) = [r for r in omabox.source_rows(omabox.load_sources(), omabox.load_state()) if r["name"] == "Rowan"]
        self.assertEqual(row["x_hidden"], {"reposts": False, "replies": False})


class CatchUpTest(unittest.TestCase):
    NOW = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)

    def items(self):
        def item(iid, source, hours_ago, **extra):
            published = (self.NOW - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
            return {"id": iid, "source": source, "published": published, "read": False, **extra}

        return [
            item("fresh", "A", 2),
            item("day-old", "A", 30),
            item("week-old", "B", 24 * 8, later=True),
            item("snoozed", "A", 48, snoozed_until="2026-09-28T08:00:00Z"),
            item("woke", "B", 48, snoozed_until="2026-09-27T08:00:00Z"),
            item("done", "A", 100, read=True),
        ]

    def unread(self, items):
        return sorted(i["id"] for i in items if not i["read"])

    def test_all_skips_only_snoozed(self):
        items = self.items()
        self.assertEqual(omabox.catch_up(items, now=self.NOW), 4)
        self.assertEqual(self.unread(items), ["snoozed"])
        self.assertTrue(next(i for i in items if i["id"] == "week-old")["later"])

    def test_older_than_a_duration(self):
        items = self.items()
        self.assertEqual(omabox.catch_up(items, omabox.parse_duration("1d"), now=self.NOW), 3)
        self.assertEqual(self.unread(items), ["fresh", "snoozed"])
        items = self.items()
        self.assertEqual(omabox.catch_up(items, omabox.parse_duration("1w"), now=self.NOW), 1)
        self.assertEqual(self.unread(items), ["day-old", "fresh", "snoozed", "woke"])

    def test_one_source(self):
        items = self.items()
        self.assertEqual(omabox.catch_up(items, source="B", now=self.NOW), 2)
        self.assertEqual(self.unread(items), ["day-old", "fresh", "snoozed"])

    def test_snooze_time_with_an_offset_is_compared_as_time(self):
        items = [{"id": "x", "source": "A", "published": "2026-09-20T08:00:00Z", "read": False,
                  "snoozed_until": "2026-09-27T13:30:00+02:00"}]
        self.assertEqual(omabox.catch_up(items, now=self.NOW), 1)


class ClearReadTest(unittest.TestCase):
    NOW = CatchUpTest.NOW
    items = CatchUpTest.items

    def cleared(self, items):
        return sorted(i["id"] for i in items if i.get("cleared"))

    def test_clears_read_posts_only(self):
        items = self.items()
        self.assertEqual(omabox.clear_read(items, now=self.NOW), 1)
        self.assertEqual(self.cleared(items), ["done"])
        self.assertEqual(omabox.clear_read(items, now=self.NOW), 0)

    def test_named_posts_are_marked_read_but_later_and_snoozed_stay(self):
        items = self.items()
        self.assertEqual(omabox.clear_read(items, ["fresh", "week-old", "snoozed"], now=self.NOW), 1)
        self.assertEqual(self.cleared(items), ["fresh"])
        self.assertTrue(next(i for i in items if i["id"] == "fresh")["read"])

    def test_command_hides_from_search_and_unread_brings_back(self):
        saved = omabox.STATE_PATH
        omabox.STATE_PATH = Path(tempfile.mkdtemp()) / "items.json"
        try:
            omabox.save_state({**omabox.load_state(), "items": self.items()})
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                omabox.main(["clear-read", "fresh"])
            self.assertEqual(out.getvalue(), "cleared 1 read post\n")
            self.assertNotIn("fresh", [i["id"] for i in omabox.search_items(omabox.load_state()["items"])])
            omabox.main(["unread", "fresh"])
            fresh = next(i for i in omabox.load_state()["items"] if i["id"] == "fresh")
        finally:
            omabox.STATE_PATH = saved
        self.assertFalse(fresh["read"])
        self.assertNotIn("cleared", fresh)

    def test_next_fetch_keeps_a_cleared_post_hidden(self):
        state = MergeTest().fresh()
        entries = list(omabox.parse_feed(ATOM_FEED))
        omabox.merge(state, "Omarchy", entries, "2026-09-02T08:00:00Z")
        omabox.clear_read(state["items"], now=self.NOW)
        self.assertEqual(omabox.merge(state, "Omarchy", entries, "2026-09-16T08:00:00Z"), 0)
        self.assertEqual([i["title"] for i in state["items"] if i.get("cleared")], ["v4.0.3"])


class DeliveryTimeTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(omabox.parse_delivery(" 7:05 "), "07:05")
        self.assertEqual(omabox.parse_delivery("23:59"), "23:59")
        for bad in ("24:00", "7", "07:60", "7pm"):
            with self.assertRaises(ValueError):
                omabox.parse_delivery(bad)

    def test_time_comes_from_state_with_eight_as_default(self):
        self.assertEqual(omabox.delivery_time({}), "08:00")
        self.assertEqual(omabox.delivery_time({"delivery": "18:30"}), "18:30")
        self.assertEqual(omabox.delivery_time({"delivery": "late"}), "08:00")

    def test_last_moment_is_today_once_the_time_passed(self):
        before = datetime(2026, 9, 26, 7, 59).astimezone()
        after = datetime(2026, 9, 26, 8, 0).astimezone()
        self.assertEqual(omabox.last_delivery_moment({}, before).day, 25)
        self.assertEqual(omabox.last_delivery_moment({}, after).day, 26)

    def test_snooze_wakes_at_the_delivery_time(self):
        now = datetime(2026, 9, 26, 23, 30).astimezone()
        morning = datetime.fromisoformat(omabox.next_morning(now, "06:45")).astimezone(now.tzinfo)
        self.assertEqual((morning.day, morning.hour, morning.minute), (27, 6, 45))


@contextlib.contextmanager
def local_clock(utc, zone="Europe/Amsterdam"):
    """The process runs in zone and omabox's datetime.now() reads utc (an aware moment)."""
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return utc.astimezone(tz) if tz else utc.astimezone().replace(tzinfo=None)

    saved = os.environ.get("TZ")
    os.environ["TZ"] = zone
    time.tzset()
    try:
        with mock.patch.object(omabox, "datetime", Clock):
            yield
    finally:
        if saved is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = saved
        time.tzset()


def utc(*fields):
    return datetime(*fields, tzinfo=timezone.utc)


class DaylightSavingTest(unittest.TestCase):
    def test_night_clocks_go_back(self):
        # 2026-10-25 03:00 CEST becomes 02:00 CET; 07:30 CET is 06:30 UTC
        with local_clock(utc(2026, 10, 25, 6, 30)):
            self.assertEqual(omabox.last_delivery_moment({}), utc(2026, 10, 24, 6, 0))
            self.assertEqual(omabox.next_delivery_moment({}), utc(2026, 10, 25, 7, 0))
            self.assertIsNone(omabox.tick_plan({"items": [], "errors": {}, "delivered": "2026-10-24T06:00:30Z"})[0])
            self.assertEqual(omabox.tick_plan({"items": [], "errors": {}, "delivered": "2026-10-24T05:59:00Z"})[0], "deliver")

    def test_night_clocks_go_forward(self):
        # 2026-03-29 02:00 CET becomes 03:00 CEST; 07:30 CEST is 05:30 UTC
        with local_clock(utc(2026, 3, 29, 5, 30)):
            self.assertEqual(omabox.last_delivery_moment({}), utc(2026, 3, 28, 7, 0))
            self.assertEqual(omabox.next_delivery_moment({}), utc(2026, 3, 29, 6, 0))
            self.assertEqual(omabox.tick_plan({"items": [], "errors": {}, "delivered": "2026-03-28T06:30:00Z"})[0], "deliver")
            self.assertEqual(omabox.tick_plan({"items": [], "errors": {}, "delivered": "2026-03-28T07:00:30Z"}), (None, omabox.TICK_MAX_SECONDS))

    def test_snooze_across_the_change(self):
        with local_clock(utc(2026, 10, 24, 21, 30)):
            self.assertEqual(omabox.next_morning(at="06:45"), "2026-10-25T05:45:00Z")
        with local_clock(utc(2026, 3, 28, 22, 30)):
            self.assertEqual(omabox.next_morning(at="06:45"), "2026-03-29T04:45:00Z")

    def test_given_zone_is_kept(self):
        zone = omabox.ZoneInfo("America/New_York")
        # 2026-11-01 02:00 EDT becomes 01:00 EST
        now = datetime(2026, 11, 1, 7, 30, tzinfo=zone)
        self.assertEqual(omabox.last_delivery_moment({}, now), utc(2026, 10, 31, 12, 0))
        self.assertEqual(omabox.next_delivery_moment({}, now), utc(2026, 11, 1, 13, 0))


class XTokenSaveTest(unittest.TestCase):
    def test_saved_for_the_owner_only_and_trimmed(self):
        path = Path(tempfile.mkdtemp()) / "omabox" / "x-token"
        omabox.save_x_token("  " + "a1" * 20 + "\n", path)
        self.assertEqual(path.read_text(), "a1" * 20 + "\n")
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        omabox.save_x_token("b2" * 20, path)
        self.assertEqual(path.read_text(), "b2" * 20 + "\n")
        self.assertEqual([p.name for p in path.parent.iterdir()], ["x-token"])

    def test_refuses_what_is_not_a_cookie_value(self):
        path = Path(tempfile.mkdtemp()) / "x-token"
        for bad in ("", "auth_token=" + "a" * 40, "a b" * 10, "short"):
            with self.assertRaises(ValueError):
                omabox.save_x_token(bad, path)
        self.assertFalse(path.exists())

    def test_missing_token_tells_the_panel_to_ask(self):
        with mock.patch.object(omabox, "discover", side_effect=omabox.XTokenMissing("X sources need your X token")), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            omabox.cmd_discover(argparse.Namespace(url="https://x.com/someone", json=True))
        self.assertEqual(json.loads(out.getvalue())["needs"], "x-token")


class TickPlanTest(unittest.TestCase):
    NOW = datetime(2026, 9, 26, 12, 0).astimezone()

    def state(self, **fields):
        state = {"items": [], "errors": {}}
        state.update(fields)
        return state

    def stamp(self, **delta):
        return (self.NOW + timedelta(**delta)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def test_first_run_delivers_at_once(self):
        self.assertEqual(omabox.tick_plan(self.state(), self.NOW)[0], "deliver")

    def test_delivered_today_waits_and_asks_again_within_the_cap(self):
        action, wait = omabox.tick_plan(self.state(delivered=self.stamp(hours=-3)), self.NOW)
        self.assertIsNone(action)
        self.assertEqual(wait, omabox.TICK_MAX_SECONDS)

    def test_missed_delivery_comes_at_the_next_tick(self):
        self.assertEqual(omabox.tick_plan(self.state(delivered=self.stamp(days=-2)), self.NOW)[0], "deliver")

    def test_delivery_before_todays_time_is_due_again(self):
        self.assertEqual(omabox.tick_plan(self.state(delivered=self.stamp(hours=-5)), self.NOW)[0], "deliver")

    def test_wait_shrinks_to_the_delivery_time(self):
        state = self.state(delivered=self.stamp(hours=-1), delivery="12:02")
        self.assertEqual(omabox.tick_plan(state, self.NOW), (None, 120))

    def test_pause_holds_until_the_first_delivery_time_after_it(self):
        old = self.stamp(days=-3)
        self.assertIsNone(omabox.tick_plan(self.state(delivered=old, paused_until=self.stamp(hours=2)), self.NOW)[0])
        # ended an hour ago, after this morning's 08:00: tomorrow's delivery is the first one
        self.assertIsNone(omabox.tick_plan(self.state(delivered=old, paused_until=self.stamp(hours=-1)), self.NOW)[0])
        # ended before this morning's 08:00
        self.assertEqual(omabox.tick_plan(self.state(delivered=old, paused_until=self.stamp(hours=-6)), self.NOW)[0],
                         "deliver")

    def test_network_errors_retry_every_half_hour(self):
        errors = {"Blog": "URLError: <urlopen error [Errno -3] Temporary failure in name resolution>"}
        state = self.state(delivered=self.stamp(hours=-1), errors=errors)
        self.assertEqual(omabox.tick_plan(state, self.NOW)[0], "retry")
        state["retried"] = self.stamp(minutes=-10)
        self.assertEqual(omabox.tick_plan(state, self.NOW), (None, omabox.TICK_MAX_SECONDS))

    def test_stamps_from_a_clock_that_ran_ahead_are_ignored(self):
        self.assertEqual(omabox.tick_plan(self.state(delivered=self.stamp(days=2)), self.NOW)[0], "deliver")
        errors = {"Blog": "URLError: <urlopen error timed out>"}
        state = self.state(delivered=self.stamp(hours=-1), retried=self.stamp(days=1), errors=errors)
        self.assertEqual(omabox.tick_plan(state, self.NOW)[0], "retry")
        self.assertTrue(omabox.is_due({"cadence": "daily"}, self.stamp(days=1), self.NOW))

    def test_other_errors_do_not_retry(self):
        state = self.state(delivered=self.stamp(hours=-1), errors={"Blog": "HTTPError: HTTP Error 404: Not Found"})
        self.assertIsNone(omabox.tick_plan(state, self.NOW)[0])


class DeliveryMessageTest(unittest.TestCase):
    def test_counts_and_names_only_sources_with_posts(self):
        self.assertEqual(omabox.delivery_message({"Omarchy": 2, "Rowan": 1, "Quiet": 0}), ("3 new posts", "Omarchy, Rowan"))
        self.assertEqual(omabox.delivery_message({"Rowan": 1}), ("1 new post", "Rowan"))


class NotificationArchiveTest(unittest.TestCase):
    def test_copies_new_and_prunes_old(self):
        root = Path(tempfile.mkdtemp())
        history, archive = root / "history", root / "archive"
        history.mkdir()
        archive.mkdir()
        now = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
        fresh = f"{int(now.timestamp() * 1000)}-5.json"
        old = f"{int((now - timedelta(days=8)).timestamp() * 1000)}-1.json"
        (history / fresh).write_text('{"summary": "hi"}')
        (history / "notes.txt").write_text("not a notification")
        (archive / old).write_text("{}")
        self.assertEqual(omabox.archive_notifications(history, archive, now), 1)
        self.assertEqual(sorted(p.name for p in archive.iterdir()), [fresh])
        self.assertEqual(omabox.archive_notifications(history, archive, now), 0)

    def test_archive_is_private(self):
        root = Path(tempfile.mkdtemp())
        history, archive = root / "history", root / "archive"
        history.mkdir()
        archive.mkdir(mode=0o755)
        archive.chmod(0o755)
        now = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
        stamp = int(now.timestamp() * 1000)
        (history / f"{stamp}-1.json").write_text('{"summary": "hi"}')
        (archive / f"{stamp}-2.json").write_text("{}")
        (archive / f"{stamp}-2.json").chmod(0o644)
        omabox.archive_notifications(history, archive, now)
        self.assertEqual(archive.stat().st_mode & 0o777, 0o700)
        self.assertEqual({p.name: p.stat().st_mode & 0o777 for p in archive.iterdir()},
                         {f"{stamp}-1.json": 0o600, f"{stamp}-2.json": 0o600})
        self.assertEqual((archive / f"{stamp}-1.json").read_text(), '{"summary": "hi"}')


class ShortPostTest(unittest.TestCase):
    def test_title_repeating_the_text_marks_a_short_post(self):
        text = "Glad to say that @tidewright now keeps the garden beds in order. Photos soon."
        self.assertTrue(omabox.is_short_post("Glad to say that @tidewright now keeps the garden beds...", text))
        self.assertFalse(omabox.is_short_post("v4.0.4", "This release brings a quieter fan curve"))
        self.assertTrue(omabox.is_short_post("RT Juno Marsh: Re @rowanvale Now the shed has a proper workbench with vices and clamps...",
                                             "RT Juno Marsh Re @rowanvale Now the shed has a proper workbench with vices and clamps."))
        self.assertFalse(omabox.is_short_post("Slow mornings", "The first frost has brought us"))

    def test_merge_gives_short_posts_one_line_and_no_excerpt(self):
        state = omabox.load_state(Path(tempfile.mkdtemp()) / "missing.json")
        text = "This has never been more true. A walk after lunch beats another meeting. " * 3
        entry = {"guid": "1", "title": text[:100] + "...", "link": "", "published": "2026-09-26T08:00:00Z",
                 "html": "<p>" + text + "</p>"}
        omabox.merge(state, "X", [entry], "2026-09-26T08:00:00Z")
        (item,) = state["items"]
        self.assertTrue(item["short"])
        self.assertEqual(item["excerpt"], "")
        self.assertLessEqual(len(item["title"]), 111)


class RsshubTest(unittest.TestCase):
    def setUp(self):
        self.runtime = Path(tempfile.mkdtemp())
        patcher = mock.patch.dict(omabox.os.environ, {"XDG_RUNTIME_DIR": str(self.runtime)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_x_profile_urls_map_to_local_route(self):
        self.assertEqual(omabox.x_profile_feed("https://x.com/rowanvale"), f"{omabox.RSSHUB_BASE}/twitter/user/rowanvale")
        self.assertEqual(omabox.x_profile_feed("https://twitter.com/rowanvale/"), f"{omabox.RSSHUB_BASE}/twitter/user/rowanvale")
        self.assertIsNone(omabox.x_profile_feed("https://x.com/home"))
        self.assertIsNone(omabox.x_profile_feed("https://x.com/rowanvale/status/1"))
        self.assertIsNone(omabox.x_profile_feed("https://github.com/rowanvale"))

    def test_needs_rsshub(self):
        self.assertTrue(omabox.needs_rsshub(f"{omabox.RSSHUB_BASE}/twitter/user/rowanvale"))
        self.assertFalse(omabox.needs_rsshub("https://world.hey.com/rowanvale/feed.atom"))

    def run_session(self, token="secret-token", up=False, start_code=0):
        calls, seen_env = [], {}
        token_path = Path(tempfile.mkdtemp()) / "x-token"
        if token is not None:
            token_path.write_text(token + "\n")

        class Result:
            def __init__(self, code):
                self.returncode, self.stderr, self.stdout = code, "boom" if code else "", ""

        def run(argv, **kwargs):
            calls.append(argv)
            if argv[:2] == ["podman", "run"]:
                env_file = Path(argv[argv.index("--env-file") + 1])
                seen_env["mode"] = env_file.stat().st_mode & 0o777
                seen_env["text"] = env_file.read_text()
                seen_env["path"] = env_file
                return Result(start_code)
            return Result(0)

        with omabox.rsshub_session(True, run=run, wait=lambda: None, up=lambda: up, token_path=token_path, engine="podman"):
            seen_env["marker"] = (self.runtime / omabox.RSSHUB_MARKER).exists()
        seen_env["marker_after"] = (self.runtime / omabox.RSSHUB_MARKER).exists()
        return calls, seen_env

    def test_session_passes_token_by_private_file_and_stops(self):
        calls, env = self.run_session()
        self.assertEqual(env["mode"], 0o600)
        self.assertIn("TWITTER_AUTH_TOKEN=secret-token", env["text"])
        self.assertFalse(env["path"].exists())
        self.assertTrue(all("secret-token" not in " ".join(argv) for argv in calls))
        self.assertEqual(calls[-1][:2], ["podman", "stop"])
        self.assertEqual((env["marker"], env["marker_after"]), (True, False))

    def test_session_reuses_running_rsshub(self):
        calls, _ = self.run_session(up=True)
        self.assertEqual(calls, [["podman", "rm", "-f", omabox.RSSHUB_CONTAINER]])

    def test_container_is_locked_down_and_keyed(self):
        calls, env = self.run_session()
        (start,) = [argv for argv in calls if argv[:2] == ["podman", "run"]]
        for flag in ("--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--memory=512m"):
            self.assertIn(flag, start)
        self.assertEqual(start[start.index("--user") + 1], "65534:65534")
        self.assertEqual(start[start.index("-p") + 1], f"127.0.0.1:{omabox.RSSHUB_PORT}:1200")
        self.assertIn("@sha256:", start[-1])
        self.assertEqual(start[start.index("--timeout") + 1], str(omabox.RSSHUB_MAX_SECONDS))
        self.assertRegex(env["text"], r"(?m)^ACCESS_KEY=[\w-]{20,}$")
        self.assertIn("DEBUG_INFO=false", env["text"])
        self.assertEqual(omabox.RSSHUB_KEY, "")

    def test_requests_carry_the_key_only_while_the_container_runs(self):
        route = f"{omabox.RSSHUB_BASE}/twitter/user/rowanvale?format=json"
        self.assertEqual(omabox.rsshub_keyed(route), route)
        with mock.patch.object(omabox, "RSSHUB_KEY", "k3y"):
            self.assertEqual(omabox.rsshub_keyed(route), route + "&key=k3y")
            self.assertEqual(omabox.rsshub_keyed(f"{omabox.RSSHUB_BASE}/twitter/user/a"),
                             f"{omabox.RSSHUB_BASE}/twitter/user/a?key=k3y")
            self.assertEqual(omabox.rsshub_keyed("https://blog.example/feed"), "https://blog.example/feed")

    def test_token_file_readable_by_others_is_tightened(self):
        token_path = Path(tempfile.mkdtemp()) / "x-token"
        token_path.write_text("secret-token\n")
        token_path.chmod(0o644)
        with omabox.rsshub_session(True, run=lambda argv, **kw: type("R", (), {"returncode": 0, "stderr": ""})(),
                                   wait=lambda: None, up=lambda: False, token_path=token_path, engine="podman"):
            pass
        self.assertEqual(token_path.stat().st_mode & 0o777, 0o600)

    def test_session_needs_token(self):
        with self.assertRaises(RuntimeError):
            self.run_session(token=None)

    def test_engine_prefers_podman_then_docker(self):
        self.assertEqual(omabox.container_engine(which=lambda tool: "/usr/bin/" + tool), "podman")
        self.assertEqual(omabox.container_engine(which=lambda tool: tool == "docker" and "/usr/bin/docker"), "docker")
        self.assertIsNone(omabox.container_engine(which=lambda tool: None))

    def test_session_without_engine_explains(self):
        real = omabox.container_engine
        omabox.container_engine = lambda: None
        try:
            with self.assertRaises(RuntimeError) as caught:
                with omabox.rsshub_session(True, run=lambda *a, **k: None, wait=lambda: None, up=lambda: False):
                    pass
        finally:
            omabox.container_engine = real
        self.assertIn("podman or docker", str(caught.exception))

    def test_failed_start_reports_without_token(self):
        with self.assertRaises(RuntimeError) as caught:
            self.run_session(start_code=125)
        self.assertNotIn("secret-token", str(caught.exception))

    def test_a_container_left_by_a_killed_run_is_removed(self):
        runtime = self.runtime
        calls = []

        def run(argv, **kwargs):
            calls.append(argv)
            return type("Result", (), {"returncode": 0})()

        omabox.stop_stale_rsshub(run)
        self.assertEqual(calls, [])
        (runtime / omabox.RSSHUB_MARKER).write_text("podman\n")
        with open(runtime / "omabox-rsshub.lock", "w") as busy:
            omabox.fcntl.flock(busy, omabox.fcntl.LOCK_EX)
            omabox.stop_stale_rsshub(run)
        self.assertEqual(calls, [])
        with mock.patch.object(omabox.shutil, "which", lambda name: f"/usr/bin/{name}"):
            omabox.stop_stale_rsshub(run)
        self.assertEqual(calls, [["podman", "rm", "-f", omabox.RSSHUB_CONTAINER]])
        self.assertFalse((runtime / omabox.RSSHUB_MARKER).exists())



class XTokenTest(unittest.TestCase):
    ROUTE = f"{omabox.RSSHUB_BASE}/twitter/user/rowanvale"

    def page(self, message):
        # RSSHub's production error page: "<name>: <message>" inside its HTML template, status 503
        return f"<html><body><h1>Looks like something went wrong</h1><pre>{message}</pre></body></html>".encode()

    def error(self, message, url=ROUTE):
        return urllib.error.HTTPError(url, 503, "Service Unavailable", {}, io.BytesIO(self.page(message)))

    def test_rejected_token_gets_the_refresh_message(self):
        for message in ("Error: Twitter API error: 401", "Error: Twitter API error: 403",
                        "Error: Twitter API user lookup failed (codes: 89)"):
            self.assertEqual(omabox.fetch_error(self.error(message), self.ROUTE), omabox.X_TOKEN_ERROR, message)
        self.assertIn("Sources (t)", omabox.X_TOKEN_ERROR)

    def test_other_failures_keep_a_plain_error(self):
        for message in ("Error: Twitter API error: 429", "NotFoundError: Twitter API could not find this user",
                        "ConfigNotFoundError: No valid Twitter token found"):
            self.assertEqual(omabox.fetch_error(self.error(message), self.ROUTE), "HTTPError: HTTP Error 503: Service Unavailable")
        with self.error("Error: Twitter API error: 401", "https://blog.example/feed") as plain:
            self.assertTrue(omabox.fetch_error(plain, "https://blog.example/feed").startswith("HTTPError:"))

    def test_token_fragment_from_rsshub_is_never_stored(self):
        stored = omabox.fetch_error(self.error("ConfigNotFoundError: Twitter cookie for token abcdefgh**** is not valid"), self.ROUTE)
        self.assertNotIn("abcdefgh", stored)

    def test_x_sources_after_a_rejection_are_not_fetched(self):
        base = omabox.RSSHUB_BASE
        sources = [{"name": "A", "url": f"{base}/twitter/user/a"}, {"name": "Repo", "url": f"{base}/github/repos/a"},
                   {"name": "B", "url": f"{base}/twitter/user/b"}]
        fetched, added = [], {}
        state = {"errors": {"B": "URLError: timed out"}}

        def fetch(state, source, stamp):
            fetched.append(source["name"])
            if source["name"] == "A":
                state["errors"]["A"] = omabox.X_TOKEN_ERROR
            return 0

        omabox.fetch_via_rsshub(state, sources, "t", added, fetch)
        self.assertEqual(fetched, ["A", "Repo"])
        self.assertEqual(state["errors"]["B"], omabox.X_TOKEN_ERROR)
        self.assertEqual(added, {"A": 0, "Repo": 0})

    def test_a_fetch_replaces_the_token_error_of_the_last_run(self):
        state = omabox.load_state(Path(tempfile.mkdtemp()) / "missing.json")
        state["errors"]["A"] = omabox.X_TOKEN_ERROR
        empty = b'{"title": "Twitter @rowanvale", "home_page_url": "https://x.com/rowanvale", "items": []}'
        sources = [{"name": "A", "url": self.ROUTE, "icon": "*"}, {"name": "B", "url": self.ROUTE, "icon": "*"}]
        fetched = []

        def fetch(state, source, stamp):
            fetched.append(source["name"])
            with contextlib.redirect_stdout(io.StringIO()):
                return omabox.fetch_source(state, source, stamp, get=lambda url, cached: (empty, {}))

        omabox.fetch_via_rsshub(state, sources, "t", {}, fetch)
        self.assertEqual(fetched, ["A", "B"])
        self.assertEqual(state["errors"], {})

    def test_one_notice_per_rejected_token(self):
        state = {"errors": {"A": omabox.X_TOKEN_ERROR, "B": omabox.X_TOKEN_ERROR, "C": "URLError: timed out"}}
        self.assertEqual(omabox.token_notice(state, notify=False), [])
        self.assertEqual(omabox.token_notice(state, notify=True), ["A", "B"])
        self.assertEqual(omabox.token_notice(state, notify=True), [])
        state["errors"] = {"C": "URLError: timed out"}
        self.assertEqual(omabox.token_notice(state, notify=True), [])
        self.assertNotIn("x_token_notified", state)
        state["errors"]["A"] = omabox.X_TOKEN_ERROR
        self.assertEqual(omabox.token_notice(state, notify=True), ["A"])

    def test_notice_text(self):
        sent = []
        omabox.notify_token_rejected(["A", "B"], send=lambda *args: sent.append(args))
        ((summary, body, view, _),) = sent
        self.assertEqual((summary, view), ("X token rejected", "sources"))
        self.assertIn("Sources, then t", body)
        self.assertIn("A, B", body)

    def test_notification_argv_opens_the_sources_view(self):
        calls = []
        omabox.send_notification("X token rejected", "body", "sources", "*", run=lambda argv, **kw: calls.append(argv))
        (argv,) = calls
        self.assertEqual(argv[0], "notify-send")
        self.assertIn('string:omarchy-exec-argv:["omarchy-shell", "omabox", "toggleView", "sources"]', argv)


class NetworkWaitTest(unittest.TestCase):
    def run_wait(self, up_after, seconds=60):
        now, lookups = [0.0], []

        def resolve(host, port):
            lookups.append(host)
            if now[0] < up_after:
                raise OSError("Temporary failure in name resolution")

        def sleep(delay):
            now[0] += delay

        return omabox.wait_for_network(["github.com"], seconds, resolve=resolve, sleep=sleep, clock=lambda: now[0]), now[0], lookups

    def test_returns_at_once_when_dns_works(self):
        ready, waited, lookups = self.run_wait(up_after=0)
        self.assertTrue(ready)
        self.assertEqual((waited, lookups), (0.0, ["github.com"]))

    def test_waits_for_dns_to_come_up(self):
        ready, waited, _ = self.run_wait(up_after=5)
        self.assertTrue(ready)
        self.assertEqual(waited, 6.0)

    def test_gives_up_after_deadline(self):
        ready, waited, _ = self.run_wait(up_after=1000, seconds=10)
        self.assertFalse(ready)
        self.assertEqual(waited, 10.0)

    def test_fetch_hosts(self):
        self.assertEqual(omabox.fetch_host("https://world.hey.com/rowanvale/feed.atom"), "world.hey.com")
        self.assertEqual(omabox.fetch_host(f"{omabox.RSSHUB_BASE}/twitter/user/rowanvale"), "x.com")
        self.assertIsNone(omabox.fetch_host(f"{omabox.RSSHUB_BASE}/github/repos/rowanvale"))

    def test_due_sources_follow_fetch_flags(self):
        sources = [{"name": "A", "cadence": "daily"}, {"name": "B", "cadence": "paused"}]
        state = {"fetched": {}}

        def args(**flags):
            return type("Args", (), {"offline": False, "all": False, "only": None, "retry": False, **flags})

        self.assertEqual([s["name"] for s in omabox.due_sources(sources, state, args())], ["A"])
        self.assertEqual(omabox.due_sources(sources, state, args(offline=True)), [])
        self.assertEqual(omabox.due_sources(sources, state, args(only=["B"])), [])

    def test_retry_picks_only_network_failures(self):
        sources = [{"name": n, "cadence": "daily"} for n in ("dns", "http", "limited", "fine")]
        state = {"fetched": {"fine": omabox.now_iso()}, "errors": {
            "dns": "URLError: <urlopen error [Errno -3] Temporary failure in name resolution>",
            "http": "HTTPError: HTTP Error 404: Not Found",
            "limited": "HTTPError: HTTP Error 429: Too Many Requests",
        }}
        args = type("Args", (), {"offline": False, "all": False, "only": None, "retry": True})
        self.assertEqual([s["name"] for s in omabox.due_sources(sources, state, args)], ["dns", "limited"])


class ConditionalGetTest(unittest.TestCase):
    CACHED = {"etag": '"v1"', "modified": "Sat, 26 Sep 2026 06:00:00 GMT", "media": omabox.MEDIA_VERSION}

    def opener(self, status=200, body=b"", headers=None):
        seen = []

        class Response:
            def __init__(self):
                self.headers = headers or {}
                self.left = body

            def read(self, amount=-1):
                chunk, self.left = self.left, b""
                return chunk

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def open_(request, timeout):
            seen.append(request)
            if status != 200:
                raise urllib.error.HTTPError(request.full_url, status, "status", {}, None)
            return Response()

        return open_, seen

    def test_sends_validators_and_304_returns_no_body(self):
        opener, seen = self.opener(status=304)
        data, validators = omabox.download_feed("https://a.example/feed", self.CACHED, opener)
        self.assertIsNone(data)
        self.assertEqual(validators, self.CACHED)
        self.assertEqual(seen[0].get_header("If-none-match"), '"v1"')
        self.assertEqual(seen[0].get_header("If-modified-since"), "Sat, 26 Sep 2026 06:00:00 GMT")

    def test_stores_new_validators_from_a_full_answer(self):
        opener, seen = self.opener(body=RSS_FEED, headers={"ETag": '"v2"'})
        data, validators = omabox.download_feed("https://a.example/feed", None, opener)
        self.assertEqual(data, RSS_FEED)
        self.assertEqual(validators, {"etag": '"v2"', "media": omabox.MEDIA_VERSION})
        self.assertIsNone(seen[0].get_header("If-none-match"))
        _, validators = omabox.download_feed("https://a.example/feed", None, self.opener(body=RSS_FEED)[0])
        self.assertEqual(validators, {})

    def test_validators_from_an_older_media_version_are_not_sent(self):
        opener, seen = self.opener(body=RSS_FEED)
        omabox.download_feed("https://a.example/feed", {**self.CACHED, "media": omabox.MEDIA_VERSION - 1}, opener)
        self.assertIsNone(seen[0].get_header("If-none-match"))
        self.assertIsNone(seen[0].get_header("If-modified-since"))

    def test_downloads_are_capped_in_size_and_time(self):
        class Trickle:
            def __init__(self, chunks):
                self.chunks = list(chunks)

            def read1(self, amount):
                return self.chunks.pop(0) if self.chunks else b""

        self.assertEqual(omabox.read_capped(Trickle([b"ab", b"cd"]), 4, 10), b"abcd")
        with self.assertRaisesRegex(ValueError, "too large"):
            omabox.read_capped(Trickle([b"ab", b"cde"]), 4, 10)
        with self.assertRaises(TimeoutError):
            omabox.read_capped(Trickle([b"ab", b"cd"]), 10, -1)

    def test_other_http_errors_still_raise(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            omabox.download_feed("https://a.example/feed", self.CACHED, self.opener(status=404)[0])
        caught.exception.close()

    def fetch(self, state, answer):
        source = {"name": "S", "url": "https://a.example/feed", "icon": "*"}
        asked = []

        def get(url, cached):
            asked.append(cached)
            return answer

        with contextlib.redirect_stdout(io.StringIO()):
            added = omabox.fetch_source(state, source, "2026-09-27T08:00:00Z", get=get)
        return added, asked

    def test_not_modified_counts_as_success(self):
        state = omabox.load_state(Path(tempfile.mkdtemp()) / "missing.json")
        state["http"]["S"] = self.CACHED
        state["errors"]["S"] = "URLError: <urlopen error timed out>"
        added, asked = self.fetch(state, (None, self.CACHED))
        self.assertEqual((added, asked), (0, [self.CACHED]))
        self.assertNotIn("S", state["errors"])
        self.assertEqual(state["fetched"]["S"], "2026-09-27T08:00:00Z")
        self.assertEqual(state["http"]["S"], self.CACHED)

    def test_full_answer_merges_and_keeps_validators_per_source(self):
        state = omabox.load_state(Path(tempfile.mkdtemp()) / "missing.json")
        added, _ = self.fetch(state, (RSS_FEED, {"etag": '"v2"', "media": omabox.MEDIA_VERSION}))
        self.assertEqual(added, 1)
        self.assertEqual(state["http"]["S"]["etag"], '"v2"')
        self.assertIn("http", omabox.SOURCE_STATE_KEYS)

    def test_failed_fetch_keeps_old_validators(self):
        state = omabox.load_state(Path(tempfile.mkdtemp()) / "missing.json")
        state["http"]["S"] = self.CACHED

        def broken(url, cached):
            raise urllib.error.URLError("timed out")

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            omabox.fetch_source(state, {"name": "S", "url": "https://a.example/feed", "icon": "*"}, "t", get=broken)
        self.assertEqual(state["http"]["S"], self.CACHED)
        self.assertTrue(state["errors"]["S"].startswith("URLError:"))


class StaleTest(unittest.TestCase):
    NOW = datetime(2026, 9, 27, 8, 0, tzinfo=timezone.utc)
    SOURCE = {"name": "S", "url": "https://a.example/feed", "cadence": "daily", "icon": "*"}

    def fresh(self):
        return omabox.load_state(Path(tempfile.mkdtemp()) / "missing.json")

    def fetch(self, state, stamp, answer):
        def get(url, cached):
            if isinstance(answer, Exception):
                raise answer
            return answer

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            omabox.fetch_source(state, self.SOURCE, stamp, get=get)

    def ago(self, **delta):
        return (self.NOW - timedelta(**delta)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def test_streak_starts_at_the_first_error_and_ends_on_success(self):
        state = self.fresh()
        self.fetch(state, "2026-09-20T08:00:00Z", urllib.error.URLError("timed out"))
        self.fetch(state, "2026-09-21T08:00:00Z", urllib.error.URLError("refused"))
        self.assertEqual(state["failing_since"], {"S": "2026-09-20T08:00:00Z"})
        self.assertIn("failing_since", omabox.SOURCE_STATE_KEYS)
        self.fetch(state, "2026-09-22T08:00:00Z", (None, {}))
        self.assertEqual((state["errors"], state["failing_since"]), ({}, {}))
        self.fetch(state, "2026-09-23T08:00:00Z", urllib.error.URLError("timed out"))
        self.fetch(state, "2026-09-24T08:00:00Z", (RSS_FEED, {}))
        self.assertEqual((state["errors"], state["failing_since"]), ({}, {}))

    def test_rsshub_shortcut_starts_a_streak_too(self):
        base = omabox.RSSHUB_BASE
        state = {"errors": {}}

        def fetch(state, source, stamp):
            state["errors"][source["name"]] = omabox.X_TOKEN_ERROR
            return 0

        omabox.fetch_via_rsshub(state, [{"name": "A", "url": f"{base}/twitter/user/a"},
                                        {"name": "B", "url": f"{base}/twitter/user/b"}], "t", {}, fetch)
        self.assertEqual(state["failing_since"], {"B": "t"})

    def test_failing_warns_from_three_days(self):
        state = self.fresh()
        state["errors"]["S"] = "HTTPError: HTTP Error 404: Not Found"
        state["failing_since"]["S"] = self.ago(days=2, hours=23)
        self.assertIsNone(omabox.staleness(self.SOURCE, state, self.NOW))
        state["failing_since"]["S"] = self.ago(days=4)
        stale = omabox.staleness(self.SOURCE, state, self.NOW)
        self.assertEqual(stale, {"kind": "failing", "days": 4})
        self.assertEqual(omabox.stale_text(stale), "failing for 4 days")

    def test_quiet_when_the_newest_post_is_old(self):
        state = self.fresh()
        state["items"] = [{"source": "S", "published": self.ago(days=200)}, {"source": "S", "published": self.ago(days=95)},
                          {"source": "Other", "published": self.ago(days=1)}]
        stale = omabox.staleness(self.SOURCE, state, self.NOW)
        self.assertEqual(stale, {"kind": "quiet", "days": 95})
        self.assertEqual(omabox.stale_text(stale), "no new posts for 95 days")
        state["items"][1]["published"] = self.ago(days=89)
        self.assertIsNone(omabox.staleness(self.SOURCE, state, self.NOW))

    def test_paused_and_empty_sources_never_warn(self):
        state = self.fresh()
        self.assertIsNone(omabox.staleness(self.SOURCE, state, self.NOW))
        state["items"] = [{"source": "S", "published": self.ago(days=400)}]
        state["errors"]["S"] = "URLError: timed out"
        state["failing_since"]["S"] = self.ago(days=30)
        self.assertIsNone(omabox.staleness({**self.SOURCE, "cadence": "paused"}, state, self.NOW))

    def test_error_without_streak_start_falls_back_to_quiet(self):
        state = self.fresh()
        state["errors"]["S"] = "URLError: timed out"
        state["items"] = [{"source": "S", "published": self.ago(days=120)}]
        self.assertEqual(omabox.staleness(self.SOURCE, state, self.NOW), {"kind": "quiet", "days": 120})

    def test_source_rows_carry_the_warning(self):
        state = self.fresh()
        state["errors"]["S"] = "URLError: timed out"
        state["failing_since"]["S"] = self.ago(days=5)
        (row,) = omabox.source_rows([self.SOURCE], state, self.NOW)
        self.assertEqual(row["stale"], {"kind": "failing", "days": 5})
        self.assertEqual(row["error"], "URLError: timed out")


class LinkTest(unittest.TestCase):
    def test_bare_urls_become_links_without_trailing_punctuation(self):
        self.assertEqual(omabox.linkify("see https://omarchy.org/news/x/."),
                         'see <a href="https://omarchy.org/news/x/">https://omarchy.org/news/x/</a>.')

    def test_existing_links_are_untouched(self):
        markup = '<a href="https://a.b/">https://a.b/</a> and @rowanvale'
        self.assertEqual(omabox.linkify(markup), markup)

    def test_mentions_only_with_base(self):
        self.assertEqual(omabox.linkify("hi @tidewright!", "https://x.com/"),
                         'hi <a href="https://x.com/tidewright">@tidewright</a>!')
        self.assertEqual(omabox.linkify("mail me@host.com", "https://x.com/"), "mail me@host.com")

    def test_card_replaces_trailing_url(self):
        page = (b'<html><head><meta property="og:title" content="tidewright joins Omarchy Core">'
                b'<meta property="og:image" content="/card.png"><meta property="og:site_name" content="Omarchy"></head></html>')

        def fetch(url, limit):
            return page

        def images(attrs):
            return f'<p><img src="omabox-img:{"a" * 20}.png" width="1200" height="630"></p>' if attrs["src"] == "https://omarchy.org/card.png" else ""

        text = "Full circle! https://omarchy.org/news/x/"
        markup = "Full circle! https://omarchy.org/news/x/"
        original = omabox.public_host
        omabox.public_host = lambda url: True
        try:
            result = omabox.attach_card(markup, text, images, fetch)
        finally:
            omabox.public_host = original
        self.assertTrue(result.startswith("Full circle! <p><img"))
        self.assertIn('<b>tidewright joins Omarchy Core</b>', result)
        self.assertIn('<span class="meta">Omarchy</span>', result)

    def test_no_card_without_title_or_trailing_url(self):
        self.assertEqual(omabox.attach_card("a https://x.org/ b", "a https://x.org/ b", None, lambda u, l: b""), "a https://x.org/ b")
        original = omabox.public_host
        omabox.public_host = lambda url: True
        try:
            self.assertEqual(omabox.attach_card("see https://x.org/", "see https://x.org/", None, lambda u, l: b"<html></html>"),
                             "see https://x.org/")
        finally:
            omabox.public_host = original


class ProfileTest(unittest.TestCase):
    FEED = (b'<rss version="2.0"><channel><title>Twitter @Rowan</title><link>https://x.com/rowanvale</link>'
            b'<image><url>https://pbs.twimg.com/profile_images/1/a.jpg</url></image>'
            b'<item><title>t</title><author>Rowan</author><link>https://x.com/rowanvale/status/1</link></item></channel></rss>')

    def test_feed_profile(self):
        self.assertEqual(omabox.feed_profile(self.FEED),
                         {"name": "Rowan", "handle": "rowanvale", "avatar_url": "https://pbs.twimg.com/profile_images/1/a.jpg"})

    def test_ensure_profile_downloads_avatar_once(self):
        calls = []

        def fetch(url, limit):
            calls.append(url)
            return png(400, 400)

        state = {"profiles": {}}
        directory = Path(tempfile.mkdtemp())
        omabox.ensure_profile(state, {"name": "Rowan on X"}, self.FEED, fetch, directory)
        omabox.ensure_profile(state, {"name": "Rowan on X"}, self.FEED, fetch, directory)
        profile = state["profiles"]["Rowan on X"]
        self.assertEqual(len(calls), 1)
        self.assertTrue(Path(profile["avatar"]).exists())
        self.assertEqual(profile["handle"], "rowanvale")


def x_entry(status, title, body, published, links=None):
    return {"id": f"https://twitter.com/rowanvale/status/{status}", "url": f"https://x.com/rowanvale/status/{status}", "title": title,
            "content_html": body, "date_published": published, "authors": [{"name": "Rowan", "url": "https://x.com/rowanvale"}],
            "_extra": {"links": links} if links else None}


QUOTE_RULE = '<hr style="border:0;border-top:1px solid #80808030;margin:12px 0;">'
# Shapes of RSSHub's Rowan timeline on 2026-09-30: a repost of a post quoting Rowan, a quote post, a plain post.
X_FEED = json.dumps({"version": "https://jsonfeed.org/version/1.1", "title": "Twitter @Rowan",
                     "home_page_url": "https://x.com/rowanvale", "icon": "https://pbs.twimg.com/profile_images/1/a.jpg", "items": [
    x_entry(300, "RT Ada Lumen: Here is my attempt at a rain theme for Omarchy",
            "RT\u2002Ada Lumen<br>Here is my attempt at a rain theme for Omarchy" + QUOTE_RULE
            + '<div class="rsshub-quote">Rowan:\u2002We need a proper rain theme in Omarchy!<br></div>',
            "2026-09-29T15:35:20.000Z",
            [{"url": "https://x.com/ada_lumen/status/250", "type": "repost",
              "content_html": '<div class="rsshub-quote">Rowan:\u2002We need a proper rain theme in Omarchy!<br></div>'}]),
    x_entry(301, "Gardening with patience and a good spade.", "Gardening with patience and a good spade." + QUOTE_RULE
            + '<div class="rsshub-quote">Moss &amp; Fern:\u2002That is how it goes.<br>'
            + '<img src="https://pbs.twimg.com/media/q.jpg"></div>',
            "2026-09-30T07:32:09.000Z", [{"url": "https://x.com/mossandfern/status/260", "type": "quote"}]),
    x_entry(302, "Hard choices, easy life.", "Hard choices, easy life.", "2026-09-30T07:58:46.000Z"),
]}).encode()


# RSSHub's reply shapes: "Re " and the prefilled @names; a self-thread reply has no names; a quoted post has no
# "Re ", only its @names. 311 also keeps the pasted link to the post it quotes.
X_REPLY_FEED = json.dumps({"items": [
    x_entry(310, "Re @ada_lumen @mossandfern Would be great if @kestrel did this.",
            "Re @ada_lumen @mossandfern Would be great if @kestrel did this.", "2026-09-30T09:00:00.000Z",
            [{"url": "https://x.com/ada_lumen/status/305", "type": "reply"}]),
    x_entry(311, "Re This puts it well: https://x.com/mossandfern/status/309?s=20",
            "Re This puts it well: https://x.com/mossandfern/status/309?s=20" + QUOTE_RULE
            + '<div class="rsshub-quote">Moss &amp; Fern:\u2002@quill_r @rowanvale Lanterns without the oil.<br></div>',
            "2026-09-30T09:10:00.000Z", [{"url": "https://x.com/mossandfern/status/309", "type": "quote"}]),
    x_entry(312, "RT Ada Lumen:  Re @mossandfern Agreed.", "RT\u2002Ada Lumen<br>Re @mossandfern Agreed.",
            "2026-09-30T09:20:00.000Z", [{"url": "https://x.com/ada_lumen/status/308", "type": "repost"}]),
]}).encode()


class XFeedTest(unittest.TestCase):
    SOURCE = "Rowan on X"

    def merged(self, entries, state=None, **options):
        state = state or omabox.load_state(Path(tempfile.mkdtemp()) / "missing.json")
        directory = Path(tempfile.mkdtemp())
        omabox.merge(state, self.SOURCE, entries, "2026-09-30T08:00:00Z",
                     lambda entry: omabox.ImageFetcher(entry["link"], lambda url, limit: jpeg(800, 400), directory),
                     mentions_base="https://x.com/", **options)
        return state, {item["id"]: item for item in state["items"]}

    def test_repost_links_the_original_and_names_its_author(self):
        repost, quoting, plain = omabox.parse_x_feed(X_FEED)
        self.assertEqual(repost["guid"], "https://twitter.com/rowanvale/status/300")
        self.assertEqual(repost["link"], "https://x.com/ada_lumen/status/250")
        self.assertEqual(repost["repost"], {"name": "Ada Lumen", "handle": "ada_lumen"})
        self.assertEqual(repost["html"], "Here is my attempt at a rain theme for Omarchy")
        # the repost holds the _extra link, so the post it quotes comes with a name only
        self.assertEqual(repost["quote"], {"name": "Rowan", "handle": "", "link": "", "reply_to": [], "avatar": "",
                                           "published": "", "html": "We need a proper rain theme in Omarchy!<br>"})
        self.assertIsNone(quoting["repost"])
        self.assertEqual(quoting["link"], "https://x.com/rowanvale/status/301")
        self.assertEqual(quoting["html"], "Gardening with patience and a good spade.")
        self.assertEqual((quoting["quote"]["name"], quoting["quote"]["handle"], quoting["quote"]["link"]),
                         ("Moss & Fern", "mossandfern", "https://x.com/mossandfern/status/260"))
        self.assertEqual((plain["repost"], plain["quote"], plain["published"]), (None, None, "2026-09-30T07:58:46Z"))

    def test_merge_keeps_the_reposted_author_and_cards_the_quote(self):
        _, items = self.merged(list(omabox.parse_x_feed(X_FEED)))
        repost = items[omabox.item_id(self.SOURCE, "https://twitter.com/rowanvale/status/300")]
        self.assertEqual(repost["title"], "Here is my attempt at a rain theme for Omarchy")
        self.assertTrue(repost["short"])
        self.assertEqual(repost["repost"], {"name": "Ada Lumen", "handle": "ada_lumen"})
        self.assertEqual(repost["link"], "https://x.com/ada_lumen/status/250")
        self.assertEqual(repost["html"], 'Here is my attempt at a rain theme for Omarchy<table width="100%" cellspacing="0" '
                         'cellpadding="0" class="quote"><tr><td class="quotecell"><p class="who"><b>Rowan</b></p>'
                         '<p class="said">We need a proper rain theme in Omarchy!</p></td></tr></table>')
        quoting = items[omabox.item_id(self.SOURCE, "https://twitter.com/rowanvale/status/301")]
        self.assertNotIn("repost", quoting)
        self.assertEqual(quoting["title"], "Gardening with patience and a good spade.")
        self.assertIn('<p class="who"><b>Moss &amp; Fern</b> <span class="meta">@mossandfern · '
                      '<a href="https://x.com/mossandfern/status/260">on X</a></span></p>', quoting["html"])
        self.assertRegex(quoting["html"], r'<img src="omabox-img:[0-9a-f]{20}\.jpg" width="800" height="400" depth="0">')

    def test_replies_lose_the_re_mark_and_name_whom_they_answer(self):
        reply, thread, repost = omabox.parse_x_feed(X_REPLY_FEED)
        self.assertEqual((reply["reply_to"], reply["html"], reply["title"]),
                         (["ada_lumen", "mossandfern"], "Would be great if @kestrel did this.",
                          "Would be great if @kestrel did this."))
        self.assertEqual((thread["reply_to"], thread["html"], thread["title"]), ([], "This puts it well:", "This puts it well:"))
        self.assertEqual((thread["quote"]["reply_to"], thread["quote"]["html"]),
                         (["quill_r", "rowanvale"], "Lanterns without the oil.<br>"))
        self.assertEqual((repost["reply_to"], repost["html"], repost["title"]),
                         (["mossandfern"], "Agreed.", "RT Ada Lumen:  Agreed."))
        self.assertEqual(omabox.parse_x_feed(X_FEED).__next__()["reply_to"], [])

    def test_replies_show_whom_they_answer_over_the_text(self):
        _, items = self.merged(list(omabox.parse_x_feed(X_REPLY_FEED)))
        reply = items[omabox.item_id(self.SOURCE, "https://twitter.com/rowanvale/status/310")]
        self.assertEqual(reply["html"], '<p class="replyto">Replying to <a href="https://x.com/ada_lumen">@ada_lumen</a>'
                         ' and <a href="https://x.com/mossandfern">@mossandfern</a></p>Would be great if '
                         '<a href="https://x.com/kestrel">@kestrel</a> did this.')
        self.assertEqual(reply["title"], "Would be great if @kestrel did this.")
        self.assertTrue(reply["short"])
        thread = items[omabox.item_id(self.SOURCE, "https://twitter.com/rowanvale/status/311")]
        self.assertTrue(thread["html"].startswith("This puts it well:<table"))
        self.assertIn('<p class="replyto">Replying to <a href="https://x.com/quill_r">@quill_r</a> and '
                      '<a href="https://x.com/rowanvale">@rowanvale</a></p><p class="said">Lanterns without the oil.</p>',
                      thread["html"])

    def test_a_pasted_link_to_the_quoted_post_goes(self):
        drop = omabox.drop_status_url
        self.assertEqual(drop("Look: https://x.com/ada/status/9?s=20", "9"), "Look:")
        self.assertEqual(drop("Look: https://twitter.com/ada/status/9<br><img src=\"a.jpg\">", "9"),
                         'Look:<br><img src="a.jpg">')
        self.assertEqual(drop("See https://x.com/ada/status/9 first", "9"), "See https://x.com/ada/status/9 first")
        self.assertEqual(drop("Look: https://x.com/ada/status/98", "9"), "Look: https://x.com/ada/status/98")

    def test_quote_cards_head_with_avatar_name_handle_and_time(self):
        status = str((1790000000000 - omabox.X_EPOCH_MS) << 22 | 4095)
        face = "https://pbs.twimg.com/profile_images/7/kestrel_normal.jpg"
        feed = json.dumps({"items": [x_entry(320, "Neat.", "Neat." + QUOTE_RULE + '<div class="rsshub-quote">'
                                             f'<img width="24" height="24" src="{face}" referrerpolicy="no-referrer">'
                                             'Kestrel:\u2002Shipped it.<br></div>', "2026-09-30T09:30:00.000Z",
                                             [{"url": f"https://x.com/kestrel/status/{status}", "type": "quote"}])]})
        entry, = omabox.parse_x_feed(feed.encode())
        self.assertEqual((entry["quote"]["name"], entry["quote"]["avatar"], entry["quote"]["published"],
                          entry["quote"]["html"]), ("Kestrel", face, "2026-09-21T14:13:20Z", "Shipped it.<br>"))
        _, items = self.merged([entry])
        card = items[omabox.item_id(self.SOURCE, "https://twitter.com/rowanvale/status/320")]["html"]
        self.assertRegex(card, r'<p class="who"><img src="omabox-avatar:[0-9a-f]{20}\.jpg" class="mini">&nbsp;'
                         r'<b>Kestrel</b> <span class="meta">@kestrel · <a href="https://x.com/kestrel/status/'
                         + status + '">' + re.escape(omabox.local_stamp("2026-09-21T14:13:20Z")) + "</a></span></p>")

    def test_status_ids_carry_their_time(self):
        self.assertEqual(omabox.status_time(str((1790000000000 - omabox.X_EPOCH_MS) << 22)), "2026-09-21T14:13:20Z")
        self.assertEqual(omabox.status_time("260"), "")

    def test_user_timelines_ask_for_quoted_avatars(self):
        base = f"{omabox.RSSHUB_BASE}/twitter"
        self.assertEqual(omabox.x_feed_url(f"{base}/user/ada"), f"{base}/user/ada/showQuotedAuthorAvatarInDesc=1?format=json")
        self.assertEqual(omabox.x_feed_url(f"{base}/list/42"), f"{base}/list/42?format=json")

    def test_replying_to_lists_names_like_x(self):
        self.assertEqual(omabox.replying_to([]), "")
        self.assertEqual(omabox.replying_to(["a"]), '<p class="replyto">Replying to @a</p>')
        self.assertEqual(omabox.replying_to(["a", "b", "c"]), '<p class="replyto">Replying to @a, @b and @c</p>')
        self.assertEqual(omabox.replying_to(["a", "b", "c", "d", "e"]),
                         '<p class="replyto">Replying to @a, @b and 3 others</p>')

    def test_mute_rules_see_the_quoted_text(self):
        _, items = self.merged(list(omabox.parse_x_feed(X_FEED)), muted=omabox.mute_filter(["proper rain"]))
        self.assertEqual(len(items), 2)
        self.assertNotIn(omabox.item_id(self.SOURCE, "https://twitter.com/rowanvale/status/300"), items)

    def test_rebuild_moves_a_stored_repost_to_the_original(self):
        iid = omabox.item_id(self.SOURCE, "https://twitter.com/rowanvale/status/300")
        state = omabox.load_state(Path(tempfile.mkdtemp()) / "missing.json")
        state["items"] = [{"id": iid, "source": self.SOURCE, "title": "RT Ada Lumen Here is my attempt",
                           "link": "https://x.com/rowanvale/status/300", "html": "RT Ada Lumen<br>Here is my attempt",
                           "published": "2026-09-29T15:35:20Z", "read": True, "short": True,
                           "media": omabox.MEDIA_VERSION - 1, "replies_html": "No replies on X yet", "replies_count": 0,
                           "replies_fetched": "2026-09-30T12:00:00Z"}]
        _, items = self.merged(list(omabox.parse_x_feed(X_FEED))[:1], state)
        self.assertEqual(items[iid]["link"], "https://x.com/ada_lumen/status/250")
        self.assertEqual(items[iid]["repost"]["handle"], "ada_lumen")
        self.assertTrue(items[iid]["read"])
        self.assertFalse(set(omabox.REPLY_KEYS) & set(items[iid]))

    def test_profile_from_json(self):
        self.assertEqual(omabox.feed_profile(X_FEED),
                         {"name": "Rowan", "handle": "rowanvale", "avatar_url": "https://pbs.twimg.com/profile_images/1/a.jpg"})

    def test_x_sources_are_fetched_as_json(self):
        state = omabox.load_state(Path(tempfile.mkdtemp()) / "missing.json")
        urls = []

        def get(url, cached):
            urls.append(url)
            return b'{"title": "Twitter @rowanvale", "home_page_url": "https://x.com/rowanvale", "items": []}', {}

        route = f"{omabox.RSSHUB_BASE}/twitter/user/rowanvale/includeRts=false"
        with contextlib.redirect_stdout(io.StringIO()):
            omabox.fetch_source(state, {"name": self.SOURCE, "url": route, "icon": "*"}, "t", get=get)
        self.assertEqual(urls, [route + "&showQuotedAuthorAvatarInDesc=1?format=json"])
        self.assertEqual(state["profiles"][self.SOURCE]["handle"], "rowanvale")


if __name__ == "__main__":
    unittest.main()


class ViewerTest(unittest.TestCase):
    PATHS = ["/c/a.png", "/c/b.jpg", "/c/c.gif"]
    URLS = ["https://video.twimg.com/a.mp4", "https://video.twimg.com/b.mp4"]

    def play(self, urls, start=0, window_after=1, exits=None, window_gone_after=None, players=None):
        """cmd_play against a fake player whose window shows after window_after looks and closes after
        window_gone_after (default: the next look); exits: poll() result."""
        launched, looks = [], []
        self.env = None

        class Player:
            def poll(self):
                return exits

            def wait(self):
                launched.append("waited")

            def terminate(self):
                launched.append("terminated")

        def run(argv, env=None, **kwargs):
            launched.append(argv)
            self.env = env
            return Player()

        def windows():
            looks.append(1)
            shown = window_after < len(looks) <= (window_gone_after or window_after + 1)
            return {"0xa", "0xplayer"} if shown else {"0xa"}

        def relay(urls):
            return [f"http://127.0.0.1:9/t/{index}.mp4" for index in range(len(urls))]

        def mpv_only(urls, start):
            return ["mpv", f"--playlist-start={start}", "--"] + urls

        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.dict(omabox.os.environ, {"http_proxy": "http://192.0.2.1:3128"}):
            omabox.cmd_play(argparse.Namespace(urls=urls, start=start), run, windows, poll_every=0, wait_seconds=5,
                            relay=relay, focus=lambda address: launched.append("focus " + address),
                            players=players or mpv_only)
        self.looks = len(looks)
        return launched, out.getvalue()

    def test_play_starts_the_player_on_the_relay_at_the_clicked_video_and_waits_for_it(self):
        launched, out = self.play(self.URLS, start=1, window_after=3)
        self.assertEqual(launched, [["mpv", "--playlist-start=1", "--", "http://127.0.0.1:9/t/0.mp4",
                                     "http://127.0.0.1:9/t/1.mp4"], "focus 0xplayer", "waited"])
        self.assertNotIn("http_proxy", self.env)
        self.assertEqual(out, "opened\n")

    def test_play_clamps_start(self):
        launched, _ = self.play(self.URLS, start=9)
        self.assertEqual(launched[0][1], "--playlist-start=1")

    def test_play_fails_when_the_player_quits_with_an_error_before_a_window(self):
        with self.assertRaises(SystemExit) as caught:
            self.play(self.URLS, window_after=99, exits=2)
        self.assertIn("could not play", str(caught.exception.code))

    def test_play_waits_on_the_window_of_a_single_instance_player(self):
        launched, out = self.play(self.URLS, window_after=2, exits=0, window_gone_after=6)
        self.assertEqual(out, "opened\n")
        self.assertEqual(launched[1:], ["focus 0xplayer", "waited"])
        self.assertEqual(self.looks, 7)

    def test_play_without_a_player_says_so(self):
        with self.assertRaises(SystemExit) as caught:
            self.play(self.URLS, players=lambda urls, start: None)
        self.assertIn("install mpv", str(caught.exception.code))

    def desktop(self, exec_line):
        path = Path(tempfile.mkdtemp()) / "app.desktop"
        path.write_text(f"[Desktop Entry]\nExec={exec_line}\n")
        return lambda mime: path

    def installed(self, *names):
        return mock.patch.object(omabox.shutil, "which", side_effect=lambda name: f"/usr/bin/{name}" if name in names else None)

    def test_player_is_the_default_video_app_with_the_clicked_video_first(self):
        with self.installed("vlc", "mpv"):
            argv = omabox.player_argv(["u0", "u1", "u2"], 1, self.desktop("vlc --started-from-file %U"))
        self.assertEqual(argv, ["vlc", "--started-from-file", "u1", "u2", "u0"])

    def test_default_mpv_keeps_the_post_order(self):
        with self.installed("mpv"):
            argv = omabox.player_argv(["u0", "u1"], 1, self.desktop("mpv --player-operation-mode=pseudo-gui -- %U"))
        self.assertEqual(argv, ["mpv", "--playlist-start=1", "--ytdl=no", "--", "u0", "u1"])

    def test_player_falls_back_to_mpv_then_none_when_the_default_app_is_gone(self):
        with self.installed("mpv"):
            self.assertEqual(omabox.player_argv(["u0"], 0, self.desktop("celluloid %U"))[0], "mpv")
        with self.installed("mpv"):
            self.assertEqual(omabox.player_argv(["u0"], 0, lambda mime: None)[0], "mpv")
        with self.installed():
            self.assertIsNone(omabox.player_argv(["u0"], 0, self.desktop("celluloid %U")))

    def test_viewer_skips_a_default_app_that_is_not_installed(self):
        with self.installed("loupe", "imv"):
            self.assertEqual(omabox.viewer_argv(self.PATHS, 0, self.desktop("loupe %U")), ["loupe"] + self.PATHS)
        with self.installed("imv"):
            self.assertEqual(omabox.viewer_argv(self.PATHS, 0, self.desktop("loupe %U"))[0], "imv")
        with self.installed():
            self.assertEqual(omabox.viewer_argv(self.PATHS, 1, self.desktop("loupe %U")), ["xdg-open", "/c/b.jpg"])

    def test_hold_focus_refocuses_mpv_when_the_closing_panel_takes_focus_away(self):
        actives, calls = iter(["0xmpv", "0xterm", "0xmpv"]), []

        def run(argv, **kwargs):
            calls.append(argv[2] if argv[1] == "dispatch" else "look")
            if argv[1] == "activewindow":
                return mock.Mock(stdout=json.dumps({"address": next(actives, "0xmpv")}))
            return mock.Mock(stdout="ok")

        omabox.hold_focus("0xmpv", run, seconds=0.05, every=0.02)
        self.assertEqual(calls[:4], ["look", "look", 'hl.dsp.focus({ window = "address:0xmpv" })', "look"])

    def test_hold_focus_gives_up_quietly_when_hyprctl_fails(self):
        def run(argv, **kwargs):
            if argv[1] == "dispatch":
                raise subprocess.TimeoutExpired(argv, 5)
            return mock.Mock(stdout=json.dumps({"address": "0xterm"}))

        omabox.hold_focus("0xmpv", run, seconds=1, every=0)

    def test_focus_window_falls_back_to_the_classic_dispatcher(self):
        sent = []

        def run(argv, **kwargs):
            sent.append(argv[2])
            return mock.Mock(stdout="ok" if argv[2].startswith("focuswindow") else "error: Invalid dispatcher")

        omabox.focus_window("0xmpv", run)
        self.assertEqual(sent, ['hl.dsp.focus({ window = "address:0xmpv" })', "focuswindow address:0xmpv"])

    def test_play_refuses_anything_but_https(self):
        for url in ("file:///etc/passwd", "--input-ipc-server=/tmp/x", "av://lavfi:sine", "http://cdn.example/a.mp4"):
            with self.assertRaises(SystemExit):
                self.play([url])

    def upstream(self, body):
        """A local video host that honours Range like a CDN; returns its base URL."""

        class Host(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path != "/v.mp4":
                    self.send_error(404)
                    return
                first, last, status = 0, len(body) - 1, 200
                ranged = re.fullmatch(r"bytes=(\d+)-(\d*)", self.headers.get("Range", ""))
                if ranged:
                    first, last, status = int(ranged[1]), int(ranged[2] or last), 206
                self.send_response(status)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Length", str(last - first + 1))
                self.send_header("Set-Cookie", "tracker=1")
                if ranged:
                    self.send_header("Content-Range", f"bytes {first}-{last}/{len(body)}")
                self.end_headers()
                self.wfile.write(body[first:last + 1])

            def log_message(self, format, *args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Host)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_port}"

    def fetch(self, url, headers=None):
        request = urllib.request.Request(url, headers=headers or {})
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=5) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as error:
            error.close()
            return error.code, error.headers, b""

    def test_relay_serves_each_video_with_ranges_for_seeking(self):
        body = bytes(range(256)) * 40
        base = self.upstream(body)
        plain = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        local = omabox.start_relay([base + "/v.mp4", base + "/gone.mp4"], opener=plain)
        self.assertRegex(local[0], r"^http://127\.0\.0\.1:\d+/[\w-]{20,}/0\.mp4$")
        status, headers, data = self.fetch(local[0])
        self.assertEqual((status, headers["Content-Type"], data), (200, "video/mp4", body))
        self.assertIsNone(headers["Set-Cookie"])
        status, headers, data = self.fetch(local[0], {"Range": "bytes=100-199"})
        self.assertEqual((status, headers["Content-Range"], data), (206, f"bytes 100-199/{len(body)}", body[100:200]))
        self.assertEqual(self.fetch(local[1])[0], 404)
        self.assertEqual(self.fetch(local[0].rsplit("/", 2)[0] + "/guess/0.mp4")[0], 404)

    def test_relay_refuses_videos_on_the_lan(self):
        local = omabox.start_relay([self.upstream(b"secret") + "/v.mp4"])
        self.assertEqual(self.fetch(local[0]), (502, mock.ANY, b""))

    def test_multi_file_viewers_get_every_picture_clicked_first(self):
        self.assertEqual(omabox.expand_exec("imv %F", self.PATHS, 1), ["imv", "/c/b.jpg", "/c/c.gif", "/c/a.png"])
        self.assertEqual(omabox.expand_exec("loupe %U", self.PATHS, 0), ["loupe"] + self.PATHS)

    def test_single_file_viewers_get_the_clicked_picture(self):
        self.assertEqual(omabox.expand_exec("eog %f", self.PATHS, 2), ["eog", "/c/c.gif"])
        self.assertEqual(omabox.expand_exec("feh", self.PATHS, 2), ["feh", "/c/c.gif"])

    def test_desktop_field_codes_and_quoting(self):
        argv = omabox.expand_exec('env A="x y" viewer --icon %i --name %c --pct 100%% %u', self.PATHS, 0)
        self.assertEqual(argv, ["env", "A=x y", "viewer", "--icon", "--name", "--pct", "100%", "/c/a.png"])

    def test_desktop_exec_reads_only_the_entry_group(self):
        path = Path(tempfile.mkdtemp()) / "v.desktop"
        path.write_text("[Desktop Entry]\nName=V\nExec=viewer %F\n\n[Desktop Action new]\nExec=viewer --new\n")
        self.assertEqual(omabox.desktop_exec(path), "viewer %F")
        path.write_text("[Desktop Action new]\nExec=viewer --new\n")
        self.assertIsNone(omabox.desktop_exec(path))


LOREM = "Omarchy ships a tiling desktop that stays out of the way while you work on the things that matter to you. "
ARTICLE_PAGE = (
    '<html><head><title>Why tiling</title><script>var x = "<p>no</p>";</script></head><body>'
    '<nav><a href="/">Home</a> <a href="/about">About</a></nav>'
    '<header class="site-header"><p>Blog of someone</p></header>'
    '<article><h1>Why tiling</h1>'
    f'<p>{LOREM * 2}<a href="/next">next part</a></p>'
    '<figure><img src="data:image/gif;base64,R0lG" data-src="img/wide.png"><figcaption>A desk</figcaption></figure>'
    f'<p>{LOREM * 2}</p>'
    '<div class="share-buttons"><p>Share this on every network you have heard of, please, it helps a lot.</p></div>'
    '</article>'
    '<aside><p>' + LOREM * 3 + '</p></aside>'
    '<footer><p>Copyright forever and ever, all rights reserved by everyone who ever lived.</p></footer>'
    '</body></html>'
).encode()
BLOCK_PAGE = (
    '<html><body><div id="top"><p><a href="/a">' + "Link " * 60 + '</a></p></div>'
    '<div class="blurb"><p>' + LOREM + '</p></div>'
    '<div class="entry"><p>' + LOREM * 2 + '</p><p>' + LOREM * 2 + '</p><p>Short.</p></div>'
    '<footer><p>' + LOREM * 4 + '</p></footer></body></html>'
).encode()
JUNK_PAGE = (
    '<html><body><nav><p>' + LOREM * 3 + '</p></nav><div class="sidebar"><p>' + LOREM + '</p></div>'
    '<footer><p>' + LOREM * 4 + '</p></footer><p>Hi.</p></body></html>'
).encode()


class ArticleTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.pages = {}
        self.calls = []

    def fetch(self, url, limit):
        self.calls.append(url)
        if url not in self.pages:
            raise urllib.error.URLError("unreachable")
        return self.pages[url]

    def image_fetch(self, url, limit):
        self.calls.append(url)
        if url == "https://blog.example/posts/img/wide.png":
            return png(800, 400)
        raise OSError("404")

    def article(self, page, url="https://blog.example/posts/why-tiling", title="Why tiling", kind="text/html; charset=utf-8"):
        self.pages[url] = (url, kind, page)
        return omabox.fetch_article(url, title, self.fetch, self.image_fetch, self.dir / "images")

    def test_article_tag_wins_and_junk_goes(self):
        fields = self.article(ARTICLE_PAGE)
        body = fields["full_html"]
        self.assertIn("Omarchy ships a tiling desktop", body)
        for junk in ("Blog of someone", "Home", "Share this", "Copyright", "no</p>", "Why tiling"):
            self.assertNotIn(junk, body)
        self.assertIn('<a href="https://blog.example/next">next part</a>', body)
        self.assertIn("<p>A desk</p>", body)
        self.assertGreaterEqual(fields["full_minutes"], 1)

    def test_relative_picture_resolved_against_page_and_cached(self):
        body = self.article(ARTICLE_PAGE)["full_html"]
        (name,) = omabox.IMAGE_REF_RE.findall(body)
        self.assertIn(f'<img src="omabox-img:{name}" width="800" height="400">', body)
        self.assertEqual((self.dir / "images" / name).read_bytes(), png(800, 400))
        self.assertIn("https://blog.example/posts/img/wide.png", self.calls)

    def test_without_article_tag_the_biggest_text_block_wins(self):
        body = self.article(BLOCK_PAGE)["full_html"]
        self.assertIn("Short.", body)
        self.assertEqual(body.count(LOREM.strip()), 4)
        self.assertNotIn("Link", body)

    def test_page_without_article_text_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "no article text"):
            self.article(JUNK_PAGE)

    def test_non_html_is_refused(self):
        with self.assertRaisesRegex(ValueError, "not a web page"):
            self.article(b"%PDF-1.7", kind="application/pdf")

    def test_private_hosts_are_refused_before_connecting(self):
        for url in ("http://127.0.0.1:9/post", "http://192.168.1.1/post", "file:///etc/passwd"):
            with self.assertRaisesRegex(ValueError, "refused"):
                omabox.download_public(url, 100)


class ArticleCommandTest(unittest.TestCase):
    LINK = "https://blog.example/posts/why-tiling"

    def setUp(self):
        root = Path(tempfile.mkdtemp())
        self.saved = {key: getattr(omabox, key) for key in ("CONFIG_PATH", "STATE_PATH", "IMAGE_DIR")}
        omabox.CONFIG_PATH, omabox.STATE_PATH, omabox.IMAGE_DIR = root / "sources.toml", root / "items.json", root / "images"
        omabox.save_sources([{"name": "Blog", "url": "https://blog.example/feed", "cadence": "daily"},
                             {"name": "Rowan", "url": f"{omabox.RSSHUB_BASE}/twitter/user/rowanvale", "cadence": "daily"}])
        state = omabox.load_state()
        day = "2026-09-26T08:00:00Z"
        state["items"] = [
            {"id": "1", "source": "Blog", "title": "Why tiling", "link": self.LINK, "html": "<p>Summary.</p>",
             "published": day, "read": False},
            {"id": "2", "source": "Blog", "title": "No link", "link": "", "html": "", "published": day, "read": False},
            {"id": "3", "source": "Rowan", "title": "Hi", "link": "https://x.com/rowanvale/status/1", "html": "", "published": day, "read": False},
            {"id": "4", "source": "Blog", "title": "LAN", "link": "http://192.168.1.1/post", "html": "", "published": day, "read": False},
        ]
        omabox.save_state(state)
        self.calls = []

    def tearDown(self):
        for key, value in self.saved.items():
            setattr(omabox, key, value)

    def fetch(self, url, limit):
        self.calls.append(url)
        return url, "text/html", ARTICLE_PAGE

    def test_stored_copy_is_served_without_network(self):
        fields, cached = omabox.load_article("1", fetch=self.fetch, image_fetch=self.fetch)
        self.assertFalse(cached)
        self.assertEqual(self.calls[0], self.LINK)
        stored = omabox.load_state()["items"][0]
        self.assertEqual(stored["full_html"], fields["full_html"])
        self.assertEqual(stored["html"], "<p>Summary.</p>")
        count = len(self.calls)
        again, cached = omabox.load_article("1", fetch=self.fetch, image_fetch=self.fetch)
        self.assertTrue(cached)
        self.assertEqual(again["full_html"], fields["full_html"])
        self.assertEqual(len(self.calls), count)
        omabox.load_article("1", refresh=True, fetch=self.fetch, image_fetch=self.fetch)
        self.assertGreater(len(self.calls), count)
        with contextlib.redirect_stdout(io.StringIO()):
            omabox.main(["article", "1", "--forget"])
        stored = omabox.load_state()["items"][0]
        self.assertNotIn("full_html", stored)
        self.assertEqual(stored["html"], "<p>Summary.</p>")

    def test_refusals_are_one_line_errors(self):
        for iid, text in (("2", "no web link"), ("3", "X posts"), ("4", "refused"), ("9", "no post 9")):
            with self.assertRaisesRegex(ValueError, text):
                omabox.load_article(iid, fetch=omabox.download_public if iid == "4" else self.fetch)
        self.assertNotIn(self.LINK, self.calls)

    def test_json_error_like_discover(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            omabox.main(["article", "2", "--json"])
        self.assertEqual(json.loads(out.getvalue()), {"error": "this post has no web link"})

    def test_fulltext_toggle_round_trips(self):
        with contextlib.redirect_stdout(io.StringIO()):
            omabox.main(["fulltext", "Blog", "on"])
        self.assertIn("full_text = true", omabox.CONFIG_PATH.read_text())
        (row,) = [r for r in omabox.source_rows(omabox.load_sources(), omabox.load_state()) if r["name"] == "Blog"]
        self.assertTrue(row["full_text"])
        with self.assertRaises(SystemExit), contextlib.redirect_stdout(io.StringIO()):
            omabox.main(["fulltext", "Rowan", "on"])
        with contextlib.redirect_stdout(io.StringIO()):
            omabox.main(["fulltext", "Blog", "off"])
        self.assertNotIn("full_text", omabox.load_sources()[0])

    def test_prune_keeps_full_article_pictures(self):
        omabox.IMAGE_DIR.mkdir()
        (omabox.IMAGE_DIR / ("a" * 20 + ".png")).write_bytes(b"x")
        state = omabox.load_state()
        state["items"][0]["full_html"] = f'<p><img src="omabox-img:{"a" * 20}.png" width="9" height="9"></p>'
        omabox.prune_images(state)
        self.assertTrue((omabox.IMAGE_DIR / ("a" * 20 + ".png")).exists())


def reply_entry(handle, status, name, text, answers=None, avatar="", published="2026-09-26T16:20:00.000Z", link_type="reply"):
    entry = {"id": f"https://twitter.com/{handle}/status/{status}", "url": f"https://x.com/{handle}/status/{status}",
             "content_html": text, "date_published": published, "authors": [{"name": name, "avatar": avatar}]}
    if answers:
        entry["_extra"] = {"links": [{"url": f"https://x.com/{answers}", "type": link_type}]}
    return entry


# X's order (RSSHub asked not to sort): the post, a thread its author answered, a promoted post, a thread a quoting
# reply joins, a repeat, and a post the focal one answers.
REPLIES_FEED = json.dumps({"version": "https://jsonfeed.org/version/1.1", "items": [
    reply_entry("rowanvale", 100, "Rowan", "Thrilled to announce", avatar="https://pbs.twimg.com/profile_images/9/rowanvale_normal.jpg",
                published="2026-09-26T16:13:00.000Z"),
    reply_entry("bp", 105, "BP", "Re @rowanvale @tidewright So many tidy notes &lt;3", "rowanvale/status/100",
                "https://pbs.twimg.com/profile_images/1/bp_normal.jpg"),
    reply_entry("rowanvale", 107, "Rowan", "Re @bp @tidewright Sketching a fix for this.", "bp/status/105",
                "https://pbs.twimg.com/profile_images/2/rowanvale_normal.jpg", "2026-09-26T16:31:00.000Z"),
    reply_entry("ads", 200, "Ad", "Try our model"),
    reply_entry("mark", 106, "Mark & co", 'Re @rowanvale<br><img src="https://pbs.twimg.com/media/a.png">', "rowanvale/status/100",
                "https://pbs.twimg.com/profile_images/3/mark_normal.png", "2026-09-26T16:25:00.000Z"),
    reply_entry("sam", 108, "Sam", "Re @mark nice one", "someone/status/7", link_type="quote"),
    reply_entry("bp", 105, "BP", "Re @rowanvale @tidewright So many tidy notes &lt;3", "rowanvale/status/100"),
    reply_entry("older", 50, "Older", "Re @someone the post this one answers", "someone/status/7"),
]}).encode()


class RepliesTest(unittest.TestCase):
    def setUp(self):
        root = Path(tempfile.mkdtemp())
        self.saved = {key: getattr(omabox, key) for key in ("STATE_PATH", "IMAGE_DIR")}
        omabox.STATE_PATH, omabox.IMAGE_DIR = root / "items.json", root / "images"
        state = omabox.load_state()
        day = "2026-09-26T16:13:00Z"
        state["items"] = [
            {"id": "x", "source": "Rowan on X", "title": "Thrilled", "link": "https://x.com/rowanvale/status/100",
             "html": "Thrilled to announce", "published": day, "read": False, "short": True},
            {"id": "blog", "source": "Blog", "title": "Post", "link": "https://blog.example/post", "html": "",
             "published": day, "read": False},
        ]
        omabox.save_state(state)
        self.urls, self.sessions = [], 0

    def tearDown(self):
        for key, value in self.saved.items():
            setattr(omabox, key, value)

    @contextlib.contextmanager
    def session(self):
        self.sessions += 1
        yield

    def fetch(self, url):
        self.urls.append(url)
        return url, REPLIES_FEED

    def picture(self, url, limit):
        return png(64, 48)

    def test_post_ref_from_status_links_only(self):
        self.assertEqual(omabox.x_post_ref("https://x.com/rowanvale/status/100"), ("rowanvale", "100"))
        self.assertEqual(omabox.x_post_ref("https://twitter.com/rowanvale/status/100?s=20"), ("rowanvale", "100"))
        self.assertIsNone(omabox.x_post_ref("https://x.com/rowanvale"))
        self.assertIsNone(omabox.x_post_ref("https://blog.example/rowanvale/status/100"))

    def test_replies_keep_x_order(self):
        replies = omabox.parse_replies(REPLIES_FEED, "100")
        self.assertEqual([r["id"] for r in replies], ["105", "107", "106", "108"])
        self.assertEqual(replies[0]["to"], "rowanvale")
        self.assertEqual(replies[0]["parent"], "100")
        self.assertEqual(replies[0]["html"], "So many tidy notes &lt;3")
        self.assertEqual(replies[0]["avatar"], "https://pbs.twimg.com/profile_images/1/bp_normal.jpg".replace("_normal", "_bigger"))
        self.assertEqual(replies[1]["parent"], "105")
        self.assertEqual(replies[2]["name"], "Mark & co")
        self.assertTrue(replies[2]["html"].startswith("<br><img"))
        self.assertEqual(replies[2]["published"], "2026-09-26T16:25:00Z")
        self.assertEqual((replies[3]["parent"], replies[3]["to"], replies[3]["avatar"]), ("", "mark", ""))

    def test_a_reply_joins_the_thread_of_the_post_it_answers(self):
        threads = omabox.thread_replies(omabox.parse_replies(REPLIES_FEED, "100"), "Rowan")
        self.assertEqual([[r["id"] for r in thread] for thread in threads], [["105", "107"], ["106", "108"]])

    def test_past_the_limit_only_threads_the_author_answered(self):
        def reply(status, handle, parent="100"):
            return {"id": status, "handle": handle, "to": "rowanvale", "parent": parent}

        replies = [reply("1", "a"), reply("2", "b"), reply("3", "c"), reply("4", "rowanvale", "3"), reply("5", "e")]
        threads = omabox.thread_replies(replies, "rowanvale", limit=1)
        self.assertEqual([[r["id"] for r in thread] for thread in threads], [["1"], ["3", "4"]])

    def test_markup_nests_replies_and_marks_the_author(self):
        threads = omabox.thread_replies(omabox.parse_replies(REPLIES_FEED, "100"), "rowanvale")
        avatars = {threads[0][0]["avatar"]: "b" * 20 + ".jpg"}
        markup = omabox.replies_markup(threads, "rowanvale", "2026-09-26T18:00:00Z", avatars=avatars)
        self.assertTrue(markup.startswith('<hr class="rule"><p class="section">Comments <span class="count">4</span></p>'))
        self.assertIn('<td class="face" valign="top"><img src="omabox-avatar:' + "b" * 20 + '.jpg"></td>', markup)
        self.assertIn("<b>Mark &amp; co</b>", markup)
        self.assertIn('<a href="https://x.com/rowanvale/status/107">', markup)
        self.assertEqual(markup.count('class="opcomment"'), 1)
        self.assertIn('<span class="opname">Rowan</span> <span class="badge">AUTHOR</span>', markup)
        self.assertIn('<p class="said">Sketching a fix for this.</p>', markup)
        # the author's answer sits inside BP's text cell, before BP's table closes
        self.assertRegex(markup, r"So many tidy notes &lt;3</p><table [^>]*class=\"opcomment\">.*?</table></td></tr></table>")
        self.assertIn('<a href="https://x.com/tidewright">', omabox.replies_markup(
            [[dict(threads[0][0], html="thanks @tidewright")]], "rowanvale", "2026-09-26T18:00:00Z"))
        self.assertNotIn("<img src=\"omabox-img", markup)
        self.assertIn("No replies on X yet", omabox.replies_markup([], "rowanvale", "2026-09-26T18:00:00Z"))

    def test_every_reply_paragraph_carries_the_class(self):
        body = 'Hi <a href="https://x.com/a">@a</a> there<br><p><img src="omabox-img:x"></p>after<p>more</p>'
        self.assertEqual(omabox.reply_paragraphs(body, "said"),
                         '<p class="said">Hi <a href="https://x.com/a">@a</a> there</p><p><img src="omabox-img:x"></p>'
                         '<p class="said">after</p><p class="said">more</p>')

    def test_fetch_stores_and_serves_the_copy(self):
        fields, cached = omabox.load_replies("x", fetch=self.fetch, session=self.session, image_fetch=self.picture)
        self.assertFalse(cached)
        self.assertEqual(self.urls, [f"{omabox.RSSHUB_BASE}/twitter/tweet/rowanvale/status/100?format=json&sorted=false"])
        self.assertEqual(fields["replies_count"], 4)
        self.assertRegex(fields["replies_html"], r'<img src="omabox-img:[0-9a-f]{20}\.png" width="64" height="48" depth="1">')
        self.assertEqual(len(set(re.findall(r'omabox-avatar:[0-9a-f]{20}\.png', fields["replies_html"]))), 3)
        stored = omabox.load_state()["items"][0]
        self.assertEqual(stored["replies_html"], fields["replies_html"])
        self.assertEqual(stored["html"], "Thrilled to announce")
        omabox.prune_images(omabox.load_state())
        self.assertEqual(len(list(omabox.IMAGE_DIR.iterdir())), 4)
        again, cached = omabox.load_replies("x", fetch=self.fetch, session=self.session)
        self.assertTrue(cached)
        self.assertEqual(again, fields)
        self.assertEqual(self.sessions, 1)
        omabox.load_replies("x", refresh=True, fetch=self.fetch, session=self.session, image_fetch=self.picture)
        self.assertEqual(self.sessions, 2)

    def test_a_repost_keeps_its_authors_avatar(self):
        state = omabox.load_state()
        state["items"][0]["repost"] = {"name": "Rowan", "handle": "rowanvale"}
        omabox.save_state(state)
        fields, _ = omabox.load_replies("x", fetch=self.fetch, session=self.session, image_fetch=self.picture)
        self.assertRegex(fields["repost_avatar"], r"^[0-9a-f]{20}\.png$")
        self.assertEqual(fields["repost_avatar"], omabox.cache_image(
            "https://pbs.twimg.com/profile_images/9/rowanvale_200x200.jpg", self.picture, omabox.IMAGE_DIR, 1)[0])
        omabox.prune_images(omabox.load_state())
        self.assertTrue((omabox.IMAGE_DIR / fields["repost_avatar"]).exists())
        self.assertEqual(omabox.load_replies("x", fetch=self.fetch, session=self.session), (fields, True))

    def test_an_avatar_that_fails_leaves_the_cell_empty(self):
        def broken(url, limit):
            raise OSError("down")

        self.assertEqual(omabox.fetch_avatars(["https://pbs.twimg.com/a_bigger.jpg"], broken), {})

    def test_failures_are_one_line_errors(self):
        for iid, text in (("blog", "only X posts"), ("nope", "no post nope")):
            with self.assertRaisesRegex(ValueError, text):
                omabox.load_replies(iid, fetch=self.fetch, session=self.session)
        self.assertEqual(self.urls, [])

        @contextlib.contextmanager
        def no_engine():
            raise RuntimeError("X sources need podman or docker")
            yield

        with self.assertRaisesRegex(ValueError, "^RSSHub: X sources need podman"):
            omabox.load_replies("x", fetch=self.fetch, session=no_engine)

        def rejected(url):
            raise urllib.error.HTTPError(url, 503, "Service Unavailable", {},
                                         io.BytesIO(b"Error: Twitter API error: 401 for token abc123"))

        with self.assertRaises(ValueError) as caught:
            omabox.load_replies("x", fetch=rejected, session=self.session)
        self.assertEqual(str(caught.exception), omabox.X_TOKEN_ERROR)
        self.assertNotIn("replies_html", omabox.load_state()["items"][0])

    def test_json_error(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            omabox.main(["replies", "blog", "--json"])
        self.assertEqual(json.loads(out.getvalue()), {"error": "only X posts have replies to show"})


class FullTextFetchTest(unittest.TestCase):
    FEED = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Blog</title>
<item><guid>1</guid><title>Why tiling</title><link>https://blog.example/posts/why-tiling</link>
<pubDate>Sat, 26 Sep 2026 08:00:00 GMT</pubDate><description>&lt;p&gt;Summary only.&lt;/p&gt;</description></item>
</channel></rss>"""

    def fetch(self, full_text, extract):
        state = omabox.load_state(Path(tempfile.mkdtemp()) / "missing.json")
        source = {"name": "Blog", "url": "https://blog.example/feed", "cadence": "daily", "icon": "*", "full_text": full_text}
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as err:
            added = omabox.fetch_source(state, source, "2026-09-26T09:00:00Z", lambda url, cached: (self.FEED, {}), extract)
        return state, added, err.getvalue()

    def test_opt_in_stores_the_article_at_delivery(self):
        state, added, _ = self.fetch(True, lambda link, title: {"full_html": f"<p>{title} in full</p>", "full_summary": "",
                                                                 "full_minutes": 3})
        (item,) = state["items"]
        self.assertEqual(added, 1)
        self.assertEqual(item["full_html"], "<p>Why tiling in full</p>")
        self.assertEqual(item["full_fetched"], "2026-09-26T09:00:00Z")
        self.assertEqual(item["html"], "<p>Summary only.</p>")

    def test_failing_extractor_keeps_the_feed_html(self):
        def broken(link, title):
            raise urllib.error.URLError("timed out")

        state, added, err = self.fetch(True, broken)
        (item,) = state["items"]
        self.assertEqual(added, 1)
        self.assertNotIn("full_html", item)
        self.assertEqual(item["html"], "<p>Summary only.</p>")
        self.assertEqual(state["errors"], {})
        self.assertIn("no full article", err)

    def test_off_by_default(self):
        def never(link, title):
            raise AssertionError("extractor called")

        state, _, _ = self.fetch(False, never)
        self.assertNotIn("full_html", state["items"][0])


class SearchPickTest(unittest.TestCase):
    NOW = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)

    def items(self):
        return [
            {"id": "old", "source": "Blog", "title": "Tiling\twindows", "html": "<p>About <b>Hyprland</b> gaps</p>",
             "published": "2026-09-20T08:00:00Z", "read": True},
            {"id": "new", "source": "Omarchy", "title": "v4.0.4", "html": "<p>Kernel fixes</p>",
             "full_html": "<p>Hyprland 0.52 inside</p>", "published": "2026-09-27T09:00:00Z", "read": False, "later": True},
            {"id": "mid", "source": "Rowan on X", "title": "Omarchy\nships", "html": "", "published": "2026-09-26T08:00:00Z",
             "read": False, "snoozed_until": "2026-09-28T08:00:00Z"},
        ]

    def test_search_matches_every_word_in_title_source_and_text(self):
        ids = lambda query: [i["id"] for i in omabox.search_items(self.items(), query)]
        self.assertEqual(ids(""), ["new", "mid", "old"])
        self.assertEqual(ids("HYPRLAND"), ["new", "old"])
        self.assertEqual(ids("omarchy"), ["new", "mid"])
        self.assertEqual(ids("hyprland gaps"), ["old"])
        self.assertEqual(ids("<b>"), [])
        row = omabox.search_row(self.items()[2], self.NOW)
        self.assertEqual((row["read"], row["later"], row["snoozed"]), (False, False, True))

    def test_options_carry_marks_and_map_the_menu_answer_back(self):
        options, ids = omabox.pick_options(omabox.search_items(self.items()), self.NOW)
        self.assertEqual(options[0], "\U000f00c0\tv4.0.4\tOmarchy · 3h ago · unread · read later")
        self.assertEqual(options[1], "●\tOmarchy ships\tRowan on X · 1d ago · unread · snoozed")
        self.assertTrue(options[2].startswith("○\tTiling windows\tBlog · "))
        self.assertTrue(all(option.count("\t") == 2 for option in options))
        self.assertEqual(omabox.pick_selection("Omarchy ships\tRowan on X · 1d ago · unread · snoozed\n", ids), "mid")
        self.assertIsNone(omabox.pick_selection("v4.0.4", ids))

    def test_same_looking_posts_stay_apart_and_the_list_is_bounded(self):
        twins = [{"id": str(n), "source": "A", "title": "Same", "published": "2026-09-27T11:00:00Z", "read": True}
                 for n in range(3)]
        options, ids = omabox.pick_options(twins, self.NOW, limit=2)
        self.assertEqual(len(options), 2)
        self.assertEqual(sorted(ids.values()), ["0", "1"])
        self.assertEqual(options[1], "○\tSame\tA · 1h ago · 2")
        self.assertEqual(omabox.menu_text("x" * 50, 10), "xxxxxxxxx…")

    def menu(self, answer):
        """A fake omarchy-shell: the summon answers like the menu (writes the selection, touches done), openPost
        records the id."""
        calls = []

        def run(argv, **kwargs):
            calls.append(argv)
            if argv[:4] == ["omarchy-shell", "shell", "summon", "omarchy.menu"]:
                payload = json.loads(argv[4])
                self.assertEqual(payload["mode"], "select")
                self.assertTrue(payload["selectionFile"].startswith(str(self.runtime)))
                if answer is not None:
                    picked = answer(payload["options"])
                    if picked is not None:
                        Path(payload["selectionFile"]).write_text(picked + "\n")
                    Path(payload["doneFile"]).touch()
                return type("Done", (), {"returncode": 0, "stdout": "ok\n", "stderr": ""})()
            return type("Done", (), {"returncode": 0, "stdout": "reading\n", "stderr": ""})()

        return run, calls

    def pick(self, answer, query="", **kwargs):
        self.runtime = Path(tempfile.mkdtemp())
        run, calls = self.menu(answer)

        def select(options, prompt, run, timeout):
            return omabox.menu_select(options, prompt, run, sleep=lambda s: None, timeout=timeout,
                                      runtime_dir=self.runtime, **kwargs)

        picked = omabox.pick_post(query, run, select, state={"items": self.items()}, now=self.NOW)
        self.assertEqual(list(self.runtime.iterdir()), [])
        return picked, calls

    def test_pick_opens_the_chosen_post_in_the_reader(self):
        picked, calls = self.pick(lambda options: options[1].split("\t", 1)[1], "omarchy")
        self.assertEqual(picked, "mid")
        self.assertEqual(calls[-1], ["omarchy-shell", "omabox", "openPost", "mid"])
        self.assertEqual(json.loads(calls[0][4])["prompt"], "Omabox: omarchy")

    def test_cancel_and_timeout_open_nothing(self):
        picked, calls = self.pick(lambda options: None)
        self.assertIsNone(picked)
        self.assertEqual(len(calls), 1)
        ticks = iter(range(0, 10000, 30))
        picked, calls = self.pick(None, clock=lambda: next(ticks))
        self.assertIsNone(picked)
        self.assertEqual(len(calls), 1)

    def test_no_match_or_no_menu_is_an_error(self):
        with self.assertRaises(ValueError):
            omabox.pick_post("nothing like this", state={"items": self.items()})

        def down(argv, **kwargs):
            return type("Done", (), {"returncode": 1, "stdout": "", "stderr": "shell not running"})()

        with self.assertRaisesRegex(ValueError, "shell not running"):
            omabox.menu_select(["x"], "p", down, runtime_dir=Path(tempfile.mkdtemp()))

