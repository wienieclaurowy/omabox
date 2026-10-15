import argparse
import codecs
import contextlib
import html
import http.server
import importlib.machinery
import importlib.util
import io
import ipaddress
import json
import os
import random
import re
import socket
import socketserver
import subprocess
import sys
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
# English whatever the machine's Omarchy language is; I18nTest points it elsewhere itself.
os.environ["OMARCHY_LANGUAGE_FILE"] = os.devnull
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

FERN = {"did": "did:plc:q4m2x7c9h3k5t8w1b6n0r2pz", "handle": "fernwick.bsky.social", "displayName": "Fernwick Bakery",
        "avatar": "https://cdn.bsky.app/img/avatar/plain/fern/a.jpg"}
GULL = {"did": "did:plc:g7u2l9l4k1e8w3x5c0v6b2nm", "handle": "harbourgull.example", "displayName": "",
        "avatar": "https://cdn.bsky.app/img/avatar/plain/gull/a.jpg"}


def bluesky_post(rkey, author, text, when, embed=None, facets=None):
    record = {"$type": "app.bsky.feed.post", "text": text, "createdAt": when}
    if facets:
        record["facets"] = facets
    post = {"uri": f"at://{author['did']}/app.bsky.feed.post/{rkey}", "author": author, "record": record,
            "indexedAt": when, "likeCount": 99, "repostCount": 7}
    if embed:
        post["embed"] = embed
    return post


RYE_TEXT = "Rye is back 🍞 at fernwick.example/rye #bread with @harbourgull.example & friends"


def facet(part, feature):
    start = RYE_TEXT.encode().index(part.encode())
    return {"index": {"byteStart": start, "byteEnd": start + len(part.encode())}, "features": [feature]}


BLUESKY_API_FEED = json.dumps({"feed": [
    {"post": bluesky_post("3p1", FERN, RYE_TEXT, "2026-09-21T18:04:00.512Z", facets=[
        facet("fernwick.example/rye", {"$type": "app.bsky.richtext.facet#link", "uri": "https://fernwick.example/rye"}),
        facet("#bread", {"$type": "app.bsky.richtext.facet#tag", "tag": "bread"}),
        facet("@harbourgull.example", {"$type": "app.bsky.richtext.facet#mention", "did": GULL["did"]})],
        embed={"$type": "app.bsky.embed.images#view", "images": [
            {"thumb": "https://cdn.bsky.app/img/feed_thumbnail/plain/fern/rye.jpg",
             "fullsize": "https://cdn.bsky.app/img/feed_fullsize/plain/fern/rye.jpg", "alt": "Two rye loaves"}]})},
    {"post": bluesky_post("3p2", GULL, "", "2026-09-20T09:00:00Z", embed={
        "$type": "app.bsky.embed.video#view", "playlist": "https://video.bsky.example/watch/gull/v/playlist.m3u8",
        "thumbnail": "https://video.bsky.example/watch/gull/v/thumbnail.jpg"}),
     "reason": {"$type": "app.bsky.feed.defs#reasonRepost", "by": FERN,
                "uri": f"at://{FERN['did']}/app.bsky.feed.repost/3r1", "indexedAt": "2026-09-21T07:30:00Z"}},
    {"post": bluesky_post("3p3", FERN, "The new oven, in full:", "2026-09-19T12:00:00Z", embed={
        "$type": "app.bsky.embed.recordWithMedia#view",
        "media": {"$type": "app.bsky.embed.external#view", "external": {
            "uri": "https://fernwick.example/oven", "title": "Our new oven", "description": "",
            "thumb": "https://cdn.bsky.app/img/feed_thumbnail/plain/fern/oven.jpg"}},
        "record": {"record": {"$type": "app.bsky.embed.record#viewRecord",
                              "uri": f"at://{GULL['did']}/app.bsky.feed.post/3q1", "author": GULL,
                              "value": {"text": "Smells good down at the harbour", "createdAt": "2026-09-19T11:00:00Z"},
                              "embeds": [{"$type": "app.bsky.embed.images#view", "images": [
                                  {"fullsize": "https://cdn.bsky.app/img/feed_fullsize/plain/gull/q.jpg", "alt": ""}]}]}}})},
    {"post": bluesky_post("3p4", FERN, "Gone, sadly", "2026-09-18T12:00:00Z", embed={
        "$type": "app.bsky.embed.record#view", "record": {"$type": "app.bsky.embed.record#viewNotFound",
                                                          "uri": f"at://{GULL['did']}/app.bsky.feed.post/3q0"}}),
     "reply": {"parent": bluesky_post("3q9", GULL, "Is the rye back?", "2026-09-18T11:00:00Z")}},
    {"post": bluesky_post("3p5", FERN, "Bakers worth following:", "2026-09-17T12:00:00Z", embed={
        "$type": "app.bsky.embed.record#view", "record": {
            "$type": "app.bsky.graph.defs#starterPackViewBasic", "uri": f"at://{FERN['did']}/app.bsky.graph.starterpack/3s1",
            "record": {"name": "Harbour bakers"}}})},
]}).encode()

HN_FEED = b"""<rss version="2.0"><channel><title>Hacker News: Front Page</title>
<item><title><![CDATA[Lantern 2.3: window groups you can name]]></title><description><![CDATA[
<p>Article URL: <a href="https://lantern.example/blog/groups?ref=hn&amp;v=2">https://lantern.example/blog/groups?ref=hn&amp;v=2</a></p>
<p>Comments URL: <a href="https://news.ycombinator.com/item?id=4100">https://news.ycombinator.com/item?id=4100</a></p>
<p>Points: 25</p>
<p># Comments: 11</p>
]]></description><pubDate>Sat, 26 Sep 2026 07:00:00 +0000</pubDate><link>https://lantern.example/blog/groups?ref=hn&amp;v=2</link>
<guid isPermaLink="false">https://news.ycombinator.com/item?id=4100</guid></item>
<item><title><![CDATA[Ask HN: What do you read once a day?]]></title><description><![CDATA[
<p>What do you read once a day?</p>
<hr><p>Comments URL: <a href="https://news.ycombinator.com/item?id=4101">https://news.ycombinator.com/item?id=4101</a></p>
<p>Points: 3</p>
<p># Comments: 0</p>
]]></description><pubDate>Sat, 26 Sep 2026 06:00:00 +0000</pubDate><link>https://news.ycombinator.com/item?id=4101</link>
<guid isPermaLink="false">https://news.ycombinator.com/item?id=4101</guid></item>
</channel></rss>"""


def recording_server(test, status=200, body=b"", headers=None):
    """A loopback HTTP server that answers every GET alike; (port, paths it was asked for)."""
    seen = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.path)
            self.send_response(status(self.path) if callable(status) else status)
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body(self.path) if callable(body) else body)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    test.addCleanup(server.server_close)
    test.addCleanup(server.shutdown)
    return server.server_port, seen


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

    def test_only_text_encodings_decode(self):
        for name in ("punycode", "idna", "zlib_codec", "utf-7", "unicode_escape", "rot13", "no-such-codec"):
            feed = f'<?xml version="1.0" encoding="{name}"?><rss version="2.0"><channel><title>Tern +AGE-</title></channel></rss>'
            self.assertEqual(omabox.feed_title(feed.encode()), "Tern +AGE-", name)
            self.assertEqual(omabox.decode_page(b"+AGE- caf\xc3\xa9", f"text/html; charset={name}"), "+AGE- caf\u00e9")
        self.assertEqual(omabox.text_codec("Windows-1250"), "cp1250")
        self.assertEqual(omabox.decode_page("\u017c\u00f3\u0142w".encode("iso-8859-2"), "text/html; charset=ISO-8859-2"), "\u017c\u00f3\u0142w")
        started = time.monotonic()
        with self.assertRaises(omabox.ET.ParseError):
            list(omabox.parse_feed(b'<?xml version="1.0" encoding="punycode"?>' + b"a" * 400_000 + b"-" + b"b" * 400_000))
        self.assertLess(time.monotonic() - started, 2)

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
        self.assertTrue(entry["html"].startswith('<video src="https://www.youtube.com/watch?v=Zq3vKe8TbWo" '
                                                 'poster="https://i.ytimg.com/vi/Zq3vKe8TbWo/hq720.jpg" '
                                                 'fallback="https://i2.ytimg.com/vi/Zq3vKe8TbWo/hqdefault.jpg"></video>'))
        self.assertIn("<p>Think of a hand tool &lt;any&gt; at all.<br>We made one.</p><p>Discuss", entry["html"])

    def test_youtube_poster_falls_back_to_the_feeds_thumbnail(self):
        asked = []

        def fetch(url, limit):
            asked.append(url)
            if "hq720" in url:
                raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
            return jpeg(480, 360)

        state = omabox.load_state(Path(tempfile.mkdtemp()) / "missing.json")
        omabox.merge(state, "Quarry", list(omabox.parse_feed(YOUTUBE_FEED)), "2026-09-27T08:00:00Z",
                     lambda entry: omabox.ImageFetcher(entry["link"], fetch, Path(tempfile.mkdtemp())))
        self.assertEqual(asked, ["https://i.ytimg.com/vi/Zq3vKe8TbWo/hq720.jpg", "https://i2.ytimg.com/vi/Zq3vKe8TbWo/hqdefault.jpg"])
        self.assertIn('<img src="omabox-poster:', state["items"][0]["html"])

    def test_youtube_thumbnail_goes_through_the_image_cache(self):
        state = omabox.load_state(Path(tempfile.mkdtemp()) / "missing.json")
        directory = Path(tempfile.mkdtemp())
        fetch = lambda url, limit: jpeg(480, 360)
        omabox.merge(state, "Quarry", list(omabox.parse_feed(YOUTUBE_FEED)), "2026-09-27T08:00:00Z",
                     lambda entry: omabox.ImageFetcher(entry["link"], fetch, directory))
        (item,) = state["items"]
        self.assertTrue(item["html"].startswith('<p><a href="https://www.youtube.com/watch?v=Zq3vKe8TbWo">'
                                                '<img src="omabox-poster:'))
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

    def test_media_content_pictures_join_a_body_without_pictures(self):
        feed = b"""<?xml version="1.0"?><rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/"><channel>
        <item><guid>1</guid><link>https://social.example/@lantern/1</link><description>&lt;p&gt;Evening walk&lt;/p&gt;</description>
          <media:content url="https://files.social.example/1.jpg" type="image/jpeg" medium="image">
            <media:description type="plain">A cat on a path</media:description></media:content>
          <media:content url="https://files.social.example/2.mp4" type="video/mp4"/>
          <media:content url="https://files.social.example/media_attachments/files/117/377/970/original/d0a6.mp4"
            type="video/mp4" medium="image"/></item>
        <item><guid>2</guid><link>https://blog.example/2</link>
          <description>&lt;p&gt;&lt;img src="https://blog.example/lead.jpg"&gt;Post&lt;/p&gt;</description>
          <media:content url="https://blog.example/lead-large.jpg" medium="image"/></item>
        </channel></rss>"""
        walk, post = omabox.parse_feed(feed)
        self.assertEqual(walk["html"], '<p>Evening walk</p><img src="https://files.social.example/1.jpg" alt="A cat on a path">'
                                       '<video src="https://files.social.example/2.mp4" poster=""></video>'
                                       '<video src="https://files.social.example/media_attachments/files/117/377/970/original/d0a6.mp4" '
                                       'poster="https://files.social.example/media_attachments/files/117/377/970/small/d0a6.png"></video>')
        self.assertNotIn("lead-large", post["html"])

    def test_hacker_news_posts_show_no_counts_and_one_link_line(self):
        gathered = omabox.gather_source(omabox.load_state(Path(tempfile.mkdtemp()) / "missing.json"),
                                        {"name": "Hacker News", "url": "https://hnrss.org/frontpage"},
                                        "2026-09-27T08:00:00Z", get=lambda url, cached: (HN_FEED, {}))
        state = omabox.load_state(Path(tempfile.mkdtemp()) / "missing.json")
        with contextlib.redirect_stdout(io.StringIO()):
            gathered.store(state)
        ask, link = sorted(state["items"], key=lambda item: item["title"])
        self.assertEqual(link["html"], '<p><a href="https://lantern.example/blog/groups?ref=hn&amp;v=2">lantern.example</a>'
                                       ' · <a href="https://news.ycombinator.com/item?id=4100">Discussion on Hacker News</a></p>')
        self.assertEqual(link["excerpt"], "lantern.example · Discussion on Hacker News")
        self.assertNotIn("Points", ask["html"])
        self.assertNotIn("Comments:", ask["html"])
        self.assertTrue(ask["html"].startswith("<p>What do you read once a day?</p>"))
        self.assertTrue(ask["html"].endswith('<p><a href="https://news.ycombinator.com/item?id=4101">Discussion on Hacker News</a></p>'))
        mastodon = {"name": "Tidepool", "url": "https://mastodon.example/@tidepool.rss"}
        self.assertFalse(omabox.is_hnrss(mastodon["url"]))

    def test_reddit_posts_end_with_one_link_line(self):
        gathered = omabox.gather_source(omabox.load_state(Path(tempfile.mkdtemp()) / "missing.json"),
                                        {"name": "r/lanterns", "url": "https://www.reddit.com/r/lanterns/.rss"},
                                        "2026-09-27T08:00:00Z", get=lambda url, cached: (REDDIT_FEED, {}))
        state = omabox.load_state(Path(tempfile.mkdtemp()) / "missing.json")
        with contextlib.redirect_stdout(io.StringIO()):
            gathered.store(state)
        link, own = sorted(state["items"], key=lambda item: item["title"])
        for item in (link, own):
            self.assertNotIn("submitted by", item["html"])
            self.assertNotIn("[comments]", item["html"])
        self.assertTrue(link["html"].endswith(
            '<p>u/wickmaker · <a href="https://lantern.example/guide">lantern.example</a>'
            ' · <a href="https://www.reddit.com/r/lanterns/comments/1ab2/a_guide/">Discussion on Reddit</a></p>'))
        self.assertTrue(own["html"].startswith("<div><p>Which wick lasts longest?</p>"))
        self.assertTrue(own["html"].endswith(
            '<p>u/emberfield · <a href="https://www.reddit.com/r/lanterns/comments/1ab3/which_wick/">Discussion on Reddit</a></p>'))
        self.assertEqual(omabox.reddit_entry({"html": "<p>no footer</p>"}), {"html": "<p>no footer</p>"})
        clip = omabox.reddit_entry({"html": '<table><tr><td><a href="https://www.reddit.com/r/lanterns/comments/1ab4/clip/">'
                                            ' <img src="https://external-preview.redd.it/clip.png?width=640&amp;s=1" alt="Clip" /> '
                                            '</a></td><td>' + reddit_footer("wickmaker", "https://v.redd.it/ab12cd",
                                            "https://www.reddit.com/r/lanterns/comments/1ab4/clip/") + "</td></tr></table>"})
        self.assertIn('<video src="https://v.redd.it/ab12cd/DASHPlaylist.mpd" '
                      'poster="https://external-preview.redd.it/clip.png?width=640&amp;s=1"></video>', clip["html"])
        self.assertIn("<p>u/wickmaker · <a href", clip["html"])
        self.assertNotIn("v.redd.it</a>", clip["html"])

    def test_reddit_footer_costs_linear_time_on_long_whitespace(self):
        footer = reddit_footer("wickmaker", "https://lantern.example/guide", "https://www.reddit.com/r/lanterns/comments/1ab2/g/")
        cut = footer.index("<span>")
        for body in ("<pre>" + " " * 200000 + "</pre>", "submitted by <a href=\"x\">u/a</a>" + " " * 200000 + "x",
                     ("submitted by" + "&#32; " * 1000) * 50, " " * 100000 + footer[:cut] + " " * 100000):
            started = time.monotonic()
            self.assertEqual(omabox.reddit_entry({"html": body})["html"], body)
            self.assertLess(time.monotonic() - started, 0.5)
        entry = omabox.reddit_entry({"html": "<p>text</p> &#32; \n " + footer})
        self.assertTrue(entry["html"].startswith("<p>text</p><p>u/wickmaker · "), entry["html"])

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


class PrivateFilesTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        config, cache = self.root / "config" / "omabox", self.root / "cache" / "omabox"
        for name, path in (("CONFIG_PATH", config / "sources.toml"), ("CACHE_DIR", cache), ("IMAGE_DIR", cache / "images"),
                           ("ICON_DIR", cache / "icons"), ("DISCOVER_DIR", cache / "discover")):
            patcher = mock.patch.object(omabox, name, path)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(os.umask, os.umask(0o022))

    def test_config_and_cache_are_private_from_creation(self):
        created = []
        real_open = omabox.os.open

        def watch(path, flags, mode=0o777, *args, **kwargs):
            created.append((Path(path).name, mode))
            return real_open(path, flags, mode, *args, **kwargs)

        with mock.patch.object(omabox.os, "open", watch):
            omabox.load_sources()
            omabox.save_sources([{"name": "Private", "url": "https://a.example/feed?token=s3cret", "cadence": "daily"}])
            omabox.cache_image("https://a.example/a.png", lambda url, limit: png(64, 64), omabox.IMAGE_DIR, 1 << 20)
            omabox.fetch_favicon("https://a.example/feed", fetch=lambda url, limit: png(32, 32))
            omabox.ensure_profile({"profiles": {}}, {"name": "Rowan"},
                                  b'{"home_page_url": "https://x.com/rowanvale", "icon": "https://a.example/me.png"}',
                                  fetch=lambda url, limit: png(48, 48))
            omabox.remember_feed(["https://a.example/feed"], RSS_FEED)
        self.assertTrue(created and all(mode == 0o600 for _, mode in created), created)
        modes = {path.name: path.stat().st_mode & 0o777 for path in self.root.rglob("*")
                 if path.name not in ("config", "cache")}
        self.assertEqual(set(modes.values()), {0o600, 0o700}, modes)
        self.assertEqual(modes["omabox"], 0o700)
        self.assertEqual(modes["sources.toml"], 0o600)

    def test_an_opml_export_is_private(self):
        omabox.save_sources([{"name": "Private", "url": "https://a.example/feed?token=s3cret", "cadence": "daily"}])
        target = self.root / "feeds.opml"
        omabox.main(["opml", "export", str(target)])
        self.assertIn("s3cret", target.read_text())
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_an_older_install_is_tightened_on_the_next_write(self):
        omabox.CONFIG_PATH.parent.mkdir(parents=True, mode=0o755)
        omabox.CONFIG_PATH.write_text('[[source]]\nname = "a"\nurl = "https://a.example/feed"\n')
        omabox.CONFIG_PATH.chmod(0o644)
        omabox.IMAGE_DIR.mkdir(parents=True)
        omabox.CACHE_DIR.chmod(0o755)
        omabox.save_sources(omabox.load_sources())
        omabox.cache_image("https://a.example/a.png", lambda url, limit: png(64, 64), omabox.IMAGE_DIR, 1 << 20)
        for path in (omabox.CONFIG_PATH.parent, omabox.CACHE_DIR, omabox.IMAGE_DIR):
            self.assertEqual(path.stat().st_mode & 0o777, 0o700, path)
        self.assertEqual(omabox.CONFIG_PATH.stat().st_mode & 0o777, 0o600)


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

    def test_control_characters_in_a_name_keep_the_file_readable(self):
        path = Path(tempfile.mkdtemp()) / "sources.toml"
        sources = [{"name": "Daily\x7f News\x01\x1f\x9f", "url": "https://news.example/feed", "cadence": "daily"}]
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

    def test_arguments_can_come_on_stdin_instead_of_argv(self):
        stdin = io.StringIO(json.dumps(["rename", "Old \u00e9", "New -- name"]) + "\n")
        with mock.patch.object(omabox.sys, "stdin", stdin), mock.patch.object(omabox, "cmd_rename") as rename:
            omabox.main([omabox.ARGS_ON_STDIN])
        self.assertEqual((rename.call_args[0][0].old, rename.call_args[0][0].new), ("Old \u00e9", "New -- name"))
        for line in ("", "not json\n", '{"a": 1}\n', '["mute", 3]\n'):
            with mock.patch.object(omabox.sys, "stdin", io.StringIO(line)), self.assertRaises(SystemExit) as caught:
                omabox.main([omabox.ARGS_ON_STDIN])
            self.assertIn("one line of JSON", str(caught.exception.code))

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
        sources, added, skipped, _ = omabox.opml_import([], text.encode())
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
        sources, added, skipped, _ = omabox.opml_import(existing, opml)
        self.assertEqual((added, skipped), (1, 3))
        self.assertEqual(sources[1], {"name": "Omarchy (2)", "url": "https://omarchy.org/feed.xml", "cadence": "daily"})
        self.assertEqual(existing[1:], [])

    def test_local_addresses_and_other_rsshub_routes_are_not_imported(self):
        base = omabox.RSSHUB_BASE
        opml = f"""<opml version="2.0"><body>
          <outline text="Router" xmlUrl="http://192.168.1.1/cgi-bin/reboot"/>
          <outline text="Here" xmlUrl="http://127.0.0.1:8080/admin/delete?all=1"/>
          <outline text="Nas" xmlUrl="http://nas:8080/feed"/>
          <outline text="Transform" xmlUrl="{base}/rsshub/transform/html/http%3A%2F%2F192.168.1.1%2F/item=a"/>
          <outline text="Odd X" xmlUrl="{base}/twitter/user/..%2F..%2Frsshub"/>
          <outline text="Odd params" xmlUrl="{base}/twitter/user/rowanvale/filter=x"/>
          <outline text="Rowan" xmlUrl="{base}/twitter/user/rowanvale/includeRts=false"/>
          <outline text="Blog" xmlUrl="https://blog.example/feed"/>
        </body></opml>""".encode()
        sources, added, skipped, refused = omabox.opml_import([], opml)
        self.assertEqual((added, skipped, refused), (2, 0, 6))
        self.assertEqual([s["name"] for s in sources], ["Rowan", "Blog"])

    def test_names_never_start_with_a_dash(self):
        opml = b"""<opml version="2.0"><body>
          <outline text="--help" xmlUrl="https://a.example/feed"/>
          <outline text="  -  " xmlUrl="https://b.example/feed"/>
        </body></opml>"""
        sources, added, *_ = omabox.opml_import([], opml)
        self.assertEqual([s["name"] for s in sources], ["help", "b.example"])
        self.assertEqual(omabox.source_name("- Tide  report"), "Tide report")

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
        sources, added, skipped, _ = omabox.opml_import([], opml, cadence="weekly")
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

        self.openers = {}

        def fake(url, headers=None, opener=None):
            self.requested.append(url)
            self.headers[url] = headers
            self.openers[url] = opener
            return url, self.pages[url]

        omabox.download = fake
        saved = omabox.DISCOVER_DIR
        omabox.DISCOVER_DIR = Path(tempfile.mkdtemp()) / "discover"
        self.addCleanup(setattr, omabox, "DISCOVER_DIR", saved)

    def tearDown(self):
        omabox.download = self.real

    def test_adding_from_the_panel_asks_the_site_once(self):
        root = Path(tempfile.mkdtemp())
        names = ("CONFIG_PATH", "STATE_PATH", "IMAGE_DIR", "ICON_DIR")
        saved = {name: getattr(omabox, name) for name in names}
        self.addCleanup(lambda: [setattr(omabox, name, value) for name, value in saved.items()])
        omabox.CONFIG_PATH, omabox.STATE_PATH = root / "sources.toml", root / "items.json"
        omabox.IMAGE_DIR, omabox.ICON_DIR = root / "images", root / "icons"
        feed = "https://www.reddit.com/r/harbourtown/.rss"
        self.pages[feed] = RSS_FEED
        conditional = []
        real_feed = omabox.download_feed
        omabox.download_feed = lambda url, cached=None: conditional.append(url) or (RSS_FEED, {})
        self.addCleanup(setattr, omabox, "download_feed", real_feed)
        found = omabox.discover("https://www.reddit.com/r/harbourtown")
        with contextlib.redirect_stdout(io.StringIO()):
            omabox.cmd_add(argparse.Namespace(url=found["url"], name="r/harbourtown", cadence="daily"))
        self.assertEqual((self.requested, conditional), ([feed], []))
        self.assertEqual([item["title"] for item in omabox.load_state()["items"]], ["Post & more"])
        stale = time.time() - omabox.DISCOVER_SECONDS - 5
        os.utime(omabox.discovered_path(feed), (stale, stale))
        self.assertIsNone(omabox.remembered_feed(feed))
        omabox.discover(feed)
        self.assertEqual(self.requested, [feed, feed])

    def test_any_run_drops_feeds_kept_past_their_minutes(self):
        omabox.remember_feed(["https://a.example/feed", "https://b.example/feed"], RSS_FEED)
        stale = time.time() - omabox.DISCOVER_SECONDS - 5
        os.utime(omabox.discovered_path("https://a.example/feed"), (stale, stale))
        with mock.patch.object(omabox, "cmd_list", lambda args: None):
            omabox.main(["list"])
        self.assertEqual(sorted(path.name for path in omabox.DISCOVER_DIR.iterdir()),
                         [omabox.discovered_path("https://b.example/feed").name])

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

    def test_reddit_and_hacker_news_get_the_names_their_sites_use(self):
        cases = {"https://old.reddit.com/r/harbourtown": "r/harbourtown", "https://reddit.com/u/fernhollow": "u/fernhollow",
                 "https://news.ycombinator.com/": "Hacker News", "https://news.ycombinator.com/ask": "Ask HN",
                 "https://news.ycombinator.com/show": "Show HN", "https://hnrss.org/newest": "Hacker News: New",
                 "https://hnrss.org/frontpage?points=200": "Hacker News: Front Page",
                 "https://mastodon.example/@tidepool.rss": "Hacker News: Front Page"}
        for url, name in cases.items():
            self.pages[omabox.site_feed(url) or url] = HN_FEED
            self.assertEqual(omabox.discover(url)["title"], name, url)

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

    def test_bluesky_profile_is_named_and_read_through_the_api(self):
        api = "https://public.api.bsky.app/xrpc/"
        self.pages[f"{api}app.bsky.actor.getProfile?actor=fernwick.bsky.social"] = json.dumps(FERN).encode()
        feed = omabox.bluesky_feed_url(FERN["did"])
        self.pages[feed] = BLUESKY_API_FEED
        found = omabox.discover("https://bsky.app/profile/fernwick.bsky.social")
        self.assertEqual((found["url"], found["title"], found["count"]),
                         (f"https://bsky.app/profile/{FERN['did']}/rss", "Fernwick Bakery", 5))
        self.assertTrue(found["latest"]["title"].startswith("Rye is back 🍞 at fernwick.example/rye #bread"))
        self.assertEqual(found["latest"]["published"], "2026-09-21T18:04:00Z")
        self.assertEqual(omabox.remembered_feed(feed), BLUESKY_API_FEED)
        self.pages[f"{api}app.bsky.actor.getProfile?actor={urllib.parse.quote(GULL['did'])}"] = json.dumps(GULL).encode()
        self.pages[omabox.bluesky_feed_url(GULL["did"])] = b'{"feed": []}'
        self.assertEqual(omabox.discover(f"https://bsky.app/profile/{GULL['did']}/rss")["title"], "harbourgull.example")

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

    def test_a_public_page_cannot_link_its_feed_off_the_web_or_into_the_lan(self):
        page = b'<html><head><link rel="alternate" type="application/rss+xml" href="%s"></head></html>'
        local = {"blog.example": "203.0.113.5", "feeds.internal.example": "192.168.1.20", "admin.internal.example": "192.168.1.1"}

        def resolve(host, *args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (local[host], 0))]

        public = mock.patch.object(omabox, "public_address", lambda address: address.startswith("203.0.113."))
        with mock.patch.object(omabox.socket, "getaddrinfo", resolve), public:
            for link in (b"file:///etc/passwd", b"http://admin.internal.example/admin", omabox.RSSHUB_BASE.encode() + b"/twitter/user/a"):
                self.pages["https://blog.example/"] = page % link
                with self.assertRaises(ValueError):
                    omabox.discover("https://blog.example/")
            self.assertEqual(self.requested, ["https://blog.example/"] * 3)
            self.pages["https://blog.example/"] = page % b"/rss"
            self.pages["https://blog.example/rss"] = RSS_FEED
            omabox.discover("https://blog.example/")
            self.assertEqual(self.openers["https://blog.example/rss"], omabox.PUBLIC_OPENER.open)
            # a page on the local network may link a feed there: self-hosted readers keep working
            self.pages["http://feeds.internal.example/"] = page % b"http://feeds.internal.example:8080/feed"
            self.pages["http://feeds.internal.example:8080/feed"] = RSS_FEED
            self.assertEqual(omabox.discover("http://feeds.internal.example/")["url"], "http://feeds.internal.example:8080/feed")

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

    @unittest.skipUnless(omabox.shutil.which("magick"), "needs ImageMagick")
    def test_tall_pictures_are_cached_scaled_down_too(self):
        tall = subprocess.run(["magick", "-size", "1000x8000", "gradient:navy-orange", "png:-"], capture_output=True,
                              check=True).stdout
        self.served["https://blog.example/tall.png"] = tall
        body, _ = omabox.sanitize('<img src="/tall.png">', self.fetcher())
        self.assertIn('width="512" height="4096"', body)

    def test_pictures_too_large_to_scale_down_are_dropped(self):
        self.served["https://blog.example/tall.png"] = png(1600, 40000)
        self.served["https://blog.example/huge.gif"] = b"GIF89a" + (4000).to_bytes(2, "little") + (5000).to_bytes(2, "little")
        with mock.patch.object(omabox.shutil, "which", lambda name: None):
            for name in ("tall.png", "huge.gif"):
                body, _ = omabox.sanitize(f'<img src="/{name}">', self.fetcher())
                self.assertNotIn("<img", body)
                self.assertIn(f'href="https://blog.example/{name}"', body)
        self.assertFalse(self.dir.exists() and any(self.dir.iterdir()))
        # one cached by an older version is not shown either
        self.dir.mkdir(parents=True)
        stem = omabox.hashlib.sha1(b"https://blog.example/tall.png").hexdigest()[:20]
        (self.dir / f"{stem}.png").write_bytes(png(1600, 40000))
        self.assertIsNone(omabox.cache_image("https://blog.example/tall.png", self.fetch, self.dir, omabox.MAX_IMAGE_BYTES))

    def test_avatars_are_few_and_small(self):
        sizes = {"https://a.example/small.png": png(400, 400), "https://a.example/tall.png": png(1600, 4000)}
        fetch = lambda url, limit: sizes.get(url, png(48, 48))
        with mock.patch.object(omabox.shutil, "which", lambda name: None):
            self.assertIsNotNone(omabox.cache_avatar("https://a.example/small.png", fetch, self.dir))
            self.assertIsNone(omabox.cache_avatar("https://a.example/tall.png", fetch, self.dir))
            urls = [f"https://a.example/{n}.png" for n in range(omabox.MAX_AVATARS_PER_ITEM + 20)]
            faces = omabox.fetch_avatars(urls[:1] + urls, fetch, self.dir)
            self.assertEqual(list(faces), urls[:omabox.MAX_AVATARS_PER_ITEM])
            fetcher = omabox.ImageFetcher("https://a.example/", fetch, self.dir)
            minis = [fetcher.avatar(url) for url in urls[:omabox.MAX_IMAGES_PER_ITEM + 3]]
            self.assertEqual(sum(bool(mini) for mini in minis), omabox.MAX_IMAGES_PER_ITEM)

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


    def connect_proxy(self):
        """A proxy that records each CONNECT and the request sent through the tunnel, answering it 204."""
        seen = []

        class Proxy(socketserver.StreamRequestHandler):
            def handle(self):
                seen.append(self.rfile.readline().decode().strip())
                while self.rfile.readline().strip():
                    pass
                self.wfile.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
                inner = [self.rfile.readline().decode().strip()]
                while line := self.rfile.readline().strip():
                    inner.append(line.decode())
                seen.append(inner)
                self.wfile.write(b"HTTP/1.1 204 No Content\r\nContent-Length: 0\r\n\r\n")

        server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Proxy)
        threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        proxy = f"http://127.0.0.1:{server.server_address[1]}"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}),
                                             omabox.PublicOnlyRedirects, omabox.PublicHTTPHandler, omabox.PublicHTTPSHandler)
        return opener, seen

    def test_a_proxy_is_never_asked_for_a_local_target(self):
        opener, seen = self.connect_proxy()
        for url in ("http://10.0.0.1/admin/video.mp4", "https://10.0.0.1/admin/video.mp4", "https://192.168.1.1/",
                    "http://intranet.invalid/feed"):
            with self.assertRaisesRegex(OSError, "non-public address refused|Name or service not known|not known"):
                opener.open(url, timeout=5)
        self.assertEqual(seen, [])

    def test_a_proxy_is_asked_for_the_address_checked_here(self):
        opener, seen = self.connect_proxy()
        answers = iter(["93.184.216.34", "10.0.0.5"])

        def resolve(host, port, *args, **kwargs):
            if host != "feeds.example":
                return real(host, port, *args, **kwargs)
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (next(answers), port or 0))]

        real = socket.getaddrinfo
        with mock.patch.object(omabox.socket, "getaddrinfo", resolve):
            opener.open("http://feeds.example/rss?a=1", timeout=5).close()
        self.assertEqual(seen[0], "CONNECT 93.184.216.34:80 HTTP/1.1")
        self.assertEqual(seen[1][0], "GET /rss?a=1 HTTP/1.1")
        self.assertIn("Host: feeds.example", seen[1])
        connection = omabox.PinnedProxyHTTPSConnection("127.0.0.1", 9)
        with mock.patch.object(omabox.socket, "getaddrinfo", resolve):
            with self.assertRaisesRegex(OSError, "non-public address refused"):
                connection.set_tunnel("feeds.example")


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


class BlueskyTest(unittest.TestCase):
    def entries(self):
        return {entry["guid"].rsplit("/", 1)[1]: entry for entry in omabox.parse_bluesky(BLUESKY_API_FEED)}

    def test_handles_are_text_in_the_reader_never_markup(self):
        evil = 'x<img src="https://tracker.example/q.gif">'
        feed = {"feed": [{"post": {"uri": "at://did:plc:a/app.bsky.feed.post/1",
                                   "author": {"did": "did:plc:a", "handle": "lantern.example"},
                                   "record": {"text": "hello", "createdAt": "2026-01-01T00:00:00Z"},
                                   "embed": {"$type": "app.bsky.embed.record#view", "record": {
                                       "$type": "app.bsky.embed.record#viewRecord", "uri": "at://did:plc:b/app.bsky.feed.post/2",
                                       "author": {"handle": evil}, "value": {"text": "quoted"}}}},
                          "reply": {"parent": {"author": {"did": "did:plc:c", "handle": 'y"><img src="https://tracker.example/r.gif">'}}}}]}
        state = {"items": []}
        omabox.merge(state, "Lantern", list(omabox.parse_bluesky(json.dumps(feed).encode())), "2026-01-01T00:00:00Z")
        markup = state["items"][0]["html"]
        self.assertNotIn("<img", markup)
        self.assertIn("@x&lt;img", markup)
        self.assertIn('href="https://bsky.app/profile/x%3Cimg%20src%3D%22https:%2F%2Ftracker.example%2Fq.gif%22%3E/post/2"', markup)
        linked = omabox.replying_to(['y"><img src=x>'], "https://x.example/")
        self.assertEqual(linked, '<p class="replyto">Replying to <a href="https://x.example/y%22%3E%3Cimg%20src%3Dx%3E">'
                                 '@y&quot;&gt;&lt;img src=x&gt;</a></p>')

    def test_text_links_its_facets_and_counts_bytes_not_characters(self):
        html = self.entries()["3p1"]["html"]
        self.assertTrue(html.startswith(
            'Rye is back 🍞 at <a href="https://fernwick.example/rye">fernwick.example/rye</a> '
            '<a href="https://bsky.app/hashtag/bread">#bread</a> with '
            f'<a href="https://bsky.app/profile/{GULL["did"]}">@harbourgull.example</a> &amp; friends'), html)
        self.assertIn('<img src="https://cdn.bsky.app/img/feed_fullsize/plain/fern/rye.jpg" alt="Two rye loaves">', html)

    def test_reposts_are_dated_and_keyed_by_the_repost(self):
        entries = self.entries()
        repost = entries["3r1"]
        self.assertEqual(repost["repost"], {"name": "harbourgull.example", "handle": "harbourgull.example"})
        self.assertEqual(repost["published"], "2026-09-21T07:30:00Z")
        self.assertEqual(repost["link"], "https://bsky.app/profile/harbourgull.example/post/3p2")
        self.assertEqual(repost["title"], "Video")
        self.assertIn('<video src="https://video.bsky.example/watch/gull/v/playlist.m3u8"', repost["html"])
        self.assertIsNone(entries["3p1"]["repost"])

    def test_quotes_cards_and_replies(self):
        entries = self.entries()
        oven = entries["3p3"]
        self.assertEqual(oven["card"], {"url": "https://fernwick.example/oven", "title": "Our new oven",
                                        "site": "fernwick.example",
                                        "thumb": "https://cdn.bsky.app/img/feed_thumbnail/plain/fern/oven.jpg"})
        self.assertEqual((oven["quote"]["name"], oven["quote"]["link"], oven["quote"]["published"]),
                         ("harbourgull.example", "https://bsky.app/profile/harbourgull.example/post/3q1", "2026-09-19T11:00:00Z"))
        self.assertIn("Smells good down at the harbour<img", oven["quote"]["html"])
        gone = entries["3p4"]
        self.assertEqual(gone["reply_to"], ["harbourgull.example"])
        self.assertEqual(gone["quote"]["html"], "<p>The quoted post is not available.</p>")
        pack = entries["3p5"]
        self.assertIsNone(pack["quote"])
        self.assertEqual((pack["card"]["url"], pack["card"]["title"]),
                         (f"https://bsky.app/starter-pack/{FERN['did']}/3s1", "Harbour bakers"))

    def test_stored_posts_carry_the_card_and_quote_and_no_counts(self):
        state = omabox.load_state(Path(tempfile.mkdtemp()) / "missing.json")
        omabox.prepare_merge(state, "Fernwick", list(omabox.parse_bluesky(BLUESKY_API_FEED)), "2026-09-27T08:00:00Z")(state)
        oven = next(item for item in state["items"] if item["guid"].endswith("/3p3"))
        self.assertIn('<p class="card"><a href="https://fernwick.example/oven"><b>Our new oven</b></a>', oven["html"])
        self.assertIn('class="quote"', oven["html"])
        self.assertNotIn("99", json.dumps(state["items"]))

    def test_source_reads_the_api_but_keeps_its_rss_address(self):
        requested = []

        def get(url, cached):
            requested.append(url)
            raise OSError("offline")

        gathered = omabox.gather_source(omabox.load_state(Path(tempfile.mkdtemp()) / "missing.json"),
                                        {"name": "Fernwick", "url": f"https://bsky.app/profile/{FERN['did']}/rss"},
                                        "2026-09-27T08:00:00Z", get=get)
        self.assertEqual(gathered.error, "OSError: offline")
        self.assertEqual(requested, [f"https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed?actor="
                                     f"{urllib.parse.quote(FERN['did'])}&filter=posts_and_author_threads&limit=30"])


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
    def test_counts_posts_and_sources_with_posts(self):
        self.assertEqual(omabox.delivery_message({"Omarchy": 2, "Rowan": 1, "Quiet": 0}), ("3 new posts", "from 2 sources"))
        self.assertEqual(omabox.delivery_message({"Rowan": 1}), ("1 new post", "from 1 source"))

    def test_source_names_stay_out_of_the_notification_command(self):
        sent = []
        name = "Harbour Support Forum"
        omabox.send_notification(*omabox.delivery_message({name: 2, "Tides": 1}), "feed", "x",
                                 run=lambda argv, **kw: sent.append(argv))
        omabox.notify_token_rejected([name], send=lambda *args: omabox.send_notification(
            *args, run=lambda argv, **kw: sent.append(argv)))
        self.assertEqual(sent[0][-2:], ["Omabox: 3 new posts", "from 2 sources"])
        self.assertTrue(sent[1][-1].endswith("1 X source waiting."), sent[1])
        self.assertFalse(any(name in arg for argv in sent for arg in argv), sent)


class I18nTest(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]

    def setUp(self):
        root = Path(tempfile.mkdtemp())
        self.language = root / "language"
        catalogs = root / "i18n"
        catalogs.mkdir()
        (catalogs / "en.json").write_text((self.ROOT / "i18n" / "en.json").read_text())
        (catalogs / "pt.json").write_text(json.dumps({"notify.xTokenRejected": "Token do X recusado"}))
        (catalogs / "pl.json").write_text(json.dumps({"notify.newPosts": {"one": "%1 nowy wpis", "few": "%1 nowe wpisy",
                                                                          "many": "%1 nowych wpisów", "other": "%1 wpisu"}}))
        for patcher in (mock.patch.object(omabox, "I18N_DIR", catalogs),
                        mock.patch.dict(os.environ, {"OMARCHY_LANGUAGE_FILE": str(self.language)})):
            patcher.start()
            self.addCleanup(patcher.stop)
        omabox.catalog.cache_clear()
        self.addCleanup(omabox.catalog.cache_clear)

    def test_catalog_matches_the_code(self):
        result = subprocess.run([sys.executable, "-I", str(self.ROOT / "tests" / "i18n_check.py"), str(self.ROOT / "i18n"),
                                 "--sources", str(self.ROOT)], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_language_is_read_for_each_message(self):
        self.language.write_text("pl\n")
        self.assertEqual([omabox.trn("notify.newPosts", n) for n in (1, 3, 5, 22)],
                         ["1 nowy wpis", "3 nowe wpisy", "5 nowych wpisów", "22 nowe wpisy"])
        self.assertEqual(omabox.tr("notify.xTokenRejected"), "X token rejected")
        self.language.write_text("pt-BR")
        self.assertEqual(omabox.tr("notify.xTokenRejected"), "Token do X recusado")
        self.assertEqual(omabox.trn("notify.newPosts", 2), "2 new posts")
        for bad in ("../etc", "PL", "", "en_US"):
            self.language.write_text(bad)
            self.assertEqual(omabox.language(), "en")
        self.language.unlink()
        self.assertEqual(omabox.delivery_message({"Rowan": 1}), ("1 new post", "from 1 source"))

    def test_plural_rules_match_the_checker(self):
        loader = importlib.machinery.SourceFileLoader("i18n_check", str(self.ROOT / "tests" / "i18n_check.py"))
        check = importlib.util.module_from_spec(importlib.util.spec_from_loader("i18n_check", loader))
        loader.exec_module(check)
        for code in check.LANGUAGES + ["en"]:
            for n in list(range(250)) + [1000000, 2000001]:
                self.assertEqual(omabox.plural_category(code, n), check.category(code, n), (code, n))

    def test_fill_never_refills_an_argument(self):
        self.assertEqual(omabox.fill("%1 and %2", ("%2", "b")), "%2 and b")
        missing = "no.such.key"
        self.assertEqual(omabox.tr(missing), missing)


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


    def test_a_cleared_popup_is_not_archived_again(self):
        root = Path(tempfile.mkdtemp())
        popup, archive = root / "popup", root / "archive"
        history = popup / "history"
        history.mkdir(parents=True)
        archive.mkdir()
        for name, path in (("NOTE_POPUP_DIR", popup), ("NOTE_HISTORY_DIR", history), ("NOTE_ARCHIVE_DIR", archive)):
            patcher = mock.patch.object(omabox, name, path)
            patcher.start()
            self.addCleanup(patcher.stop)
        stamp = int(time.time() * 1000)
        forgotten, cleared, kept = (f"{stamp}-{n}.json" for n in (1, 2, 3))
        for name in (forgotten, cleared):
            (popup / name).write_text('{"summary": "Sign-in code"}')
        (popup / "notes.txt").write_text("not a notification")
        (history / kept).write_text("{}")
        omabox.archive_notifications(history, archive)
        omabox.main(["forget-notification", forgotten])
        self.assertEqual(sorted(p.name for p in popup.iterdir() if p.is_file()), [cleared, "notes.txt"])
        omabox.main(["clear-notifications"])
        self.assertEqual(sorted(p.name for p in popup.iterdir() if p.is_file()), ["notes.txt"])
        omabox.archive_notifications(history, archive)
        self.assertEqual([p.name for p in archive.iterdir()], [kept])


class HostileRunsTest(unittest.TestCase):
    """Long runs of spaces, breaks, rules or unclosed comments: each took minutes when a pattern was tried from every
    position of the run; a linear pass takes well under a second."""
    N = 100_000

    def assertQuick(self, call):
        started = time.monotonic()
        call()
        self.assertLess(time.monotonic() - started, 2)

    def test_shaping_a_post_is_linear_in_its_runs(self):
        n, state = self.N, {"items": [], **{key: {} for key in omabox.SOURCE_STATE_KEYS}}
        entry = {"guid": "1", "title": "a" + " ." * n + "b", "link": "", "published": "2026-01-01T00:00:00Z",
                 "html": "<ul><li>a" + " " * n + "b</li></ul>" + " <br>" * n + "c",
                 "quote": {"name": "q", "handle": "q", "html": "q", "link": "https://x.com/q/status/1"}}
        self.assertQuick(lambda: omabox.merge(state, "Tides", [entry], "2026-01-01T00:00:00Z"))
        self.assertQuick(lambda: omabox.hn_entry({"html": "a" + " " * n + "<p>x</p>" + " <hr />" * n + "b"}))
        self.assertQuick(lambda: omabox.reply_paragraphs("a" + "<br> " * n + "b", "reply"))
        self.assertQuick(lambda: omabox.drop_status_url("a" + " " * n + "b", "123"))
        self.assertQuick(lambda: omabox.repair_xml("<!--" * n + "<![CDATA[" * n))
        feed = {"items": [{"id": "1", "content_html": "<hr " * n + '<div class="rsshub-quote">' * n}]}
        self.assertQuick(lambda: list(omabox.parse_x_feed(json.dumps(feed).encode())))

    def test_trailing_runs_still_go(self):
        self.assertEqual(omabox.hn_entry({"html": "<p>Story</p> <hr/>\n<hr >  <hr>"})["html"], "<p>Story</p>")
        self.assertEqual(omabox.reply_paragraphs("<br> a <br> b<br> ", "r"), '<p class="r">a <br> b</p>')
        self.assertEqual(omabox.TRAILING_BREAKS_RE.sub("", "a <br>\n<br> "), "a")
        self.assertEqual(omabox.TRAILING_BREAKS_RE.sub("", "a  "), "a  ")
        self.assertEqual(list(omabox.xml_raw_split("a<!--x<![CDATA[y]]>--><![CDATA[z]]>b<!--")),
                         [(False, "a"), (True, "<!--x<![CDATA[y]]>-->"), (False, ""), (True, "<![CDATA[z]]>"),
                          (False, "b<!--")])


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

    def run_session(self, token="secret-token", start_code=0, check=lambda: None):
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

        with omabox.rsshub_session(True, run=run, wait=lambda: None, check=check, token_path=token_path, engine="podman"):
            seen_env["marker"] = (self.runtime / omabox.RSSHUB_MARKER).exists()
            seen_env["live"] = (omabox.RSSHUB_LIVE_PORT, omabox.RSSHUB_KEY)
        seen_env["marker_after"] = (self.runtime / omabox.RSSHUB_MARKER).exists()
        return calls, seen_env

    def test_session_passes_token_by_private_file_and_stops(self):
        calls, env = self.run_session()
        self.assertEqual(env["mode"], 0o600)
        self.assertIn("TWITTER_AUTH_TOKEN=secret-token", env["text"])
        self.assertFalse(env["path"].exists())
        self.assertTrue(all("secret-token" not in " ".join(argv) for argv in calls))
        started = next(argv for argv in calls if argv[:2] == ["podman", "run"])
        self.assertIn("--log-driver=none", started)
        self.assertEqual(calls[-1][:2], ["podman", "stop"])
        self.assertEqual((env["marker"], env["marker_after"]), (True, False))

    def test_session_never_uses_a_listener_it_did_not_start(self):
        seen = []

        class Squatter(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append(self.path)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"items": []}')

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Squatter)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        port = server.server_port
        route = f"http://127.0.0.1:{port}/twitter/user/rowanvale?format=json"
        with mock.patch.object(omabox, "RSSHUB_PORT", port):
            with self.assertRaises(RuntimeError):
                omabox.download(route)
            calls, env = self.run_session()
            self.assertTrue(any(argv[:2] == ["podman", "run"] for argv in calls))
            self.assertNotEqual(env["live"][0], port)
            # the port is held by another account once the container is up: refused before any route is asked
            other = os.getuid() + 4242
            with mock.patch.object(omabox, "free_port", lambda: port), mock.patch.object(omabox.os, "getuid", lambda: other):
                with self.assertRaises(RuntimeError) as caught:
                    self.run_session(check=omabox.check_rsshub)
                with mock.patch.object(omabox, "RSSHUB_KEY", "k3y"), mock.patch.object(omabox, "RSSHUB_LIVE_PORT", port):
                    with self.assertRaises(RuntimeError):
                        omabox.rsshub_up()
                    with self.assertRaisesRegex(OSError, "held by another account"):
                        omabox.download(route)
        self.assertIn("not Omabox's RSSHub container", str(caught.exception))
        self.assertEqual(seen, [])

    def test_ownership_is_the_listening_account(self):
        with mock.patch.object(omabox, "RSSHUB_LIVE_PORT", 40001):
            for uids in ({os.getuid()}, {0}, {0, os.getuid()}):
                omabox.check_rsshub(lambda port: uids)
            for uids in (set(), {os.getuid() + 4242}, {os.getuid(), os.getuid() + 4242}):
                with self.assertRaisesRegex(RuntimeError, "not Omabox's RSSHub container"):
                    omabox.check_rsshub(lambda port: uids)

    def test_proc_net_tcp_rows_name_both_ends_and_their_accounts(self):
        table = Path(tempfile.mkdtemp()) / "tcp"
        table.write_text(
            "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
            "   0: 0100007F:9C41 00000000:0000 0A 00000000:00000000 00:00000000 00000000  4242        0 1\n"
            "   1: 0100007F:9C41 0100007F:D431 01 00000000:00000000 00:00000000 00000000  4242        0 2\n"
            "   2: 00000000:1F90 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 3\n")
        table6 = Path(tempfile.mkdtemp()) / "tcp6"
        table6.write_text(
            "  sl  local_address                         remote_address                        st tx_queue rx_queue tr "
            "tm->when retrnsmt   uid  timeout inode\n"
            "   0: 0000000000000000FFFF00000100007F:1F91 00000000000000000000000000000000:0000 0A 00000000:00000000 "
            "00:00000000 00000000  1000        0 4\n")
        with mock.patch.object(omabox, "PROC_NET_TCP", (table, table6)):
            self.assertEqual(omabox.listener_uids(0x9C41), {4242})
            self.assertEqual(omabox.listener_uids(0x1F90), {0})
            self.assertEqual(omabox.listener_uids(0x1F91), {1000})
            sock = mock.Mock(getsockname=lambda: ("127.0.0.1", 0xD431), getpeername=lambda: ("127.0.0.1", 0x9C41))
            self.assertEqual(omabox.peer_uid(sock), 4242)

    def test_a_real_loopback_peer_is_this_account(self):
        port, asked = recording_server(self)
        with socket.create_connection(("127.0.0.1", port)) as sock:
            self.assertEqual(omabox.peer_uid(sock), os.getuid())
        self.assertIn(os.getuid(), omabox.listener_uids(port))
        # an end that closed before the check, as pasta does while the container starts, gets nothing either
        with mock.patch.object(omabox, "peer_uid", lambda sock: None), self.assertRaises(urllib.error.URLError):
            omabox.LOOPBACK_OPENER.open(f"http://127.0.0.1:{port}/", timeout=5)
        self.assertEqual(asked, [])

    def test_rootful_docker_runs_rsshub_as_an_id_no_host_account_holds(self):
        def docker(options):
            def run(argv, **kwargs):
                if argv[1] == "info":
                    return subprocess.CompletedProcess(argv, 0, options, "")
                return subprocess.CompletedProcess(argv, 0, "", "")
            return run

        self.assertEqual(omabox.container_user(docker(""), "podman"), "65534:65534")
        for remapped in ('["name=seccomp,profile=builtin","name=rootless","name=cgroupns"]', '["name=userns"]'):
            self.assertEqual(omabox.container_user(docker(remapped), "docker"), "65534:65534")
        user = omabox.container_user(docker('["name=seccomp,profile=builtin","name=cgroupns"]'), "docker")
        uid, gid = map(int, user.split(":"))
        self.assertEqual(uid, gid)
        self.assertTrue(omabox.UNUSED_ID_RANGE[0] <= uid < omabox.UNUSED_ID_RANGE[1])
        for lookup in (omabox.pwd.getpwuid, omabox.grp.getgrgid):
            with self.assertRaises(KeyError):
                lookup(uid)

        def unanswered(argv, **kwargs):
            raise OSError("no docker daemon")

        self.assertNotEqual(omabox.container_user(unanswered, "docker"), "65534:65534")

    def test_unused_id_skips_accounts_groups_and_subordinate_ranges(self):
        listing = Path(tempfile.mkdtemp()) / "subuid"
        listing.write_text("someone:1879048192:65536\nbroken line\n")
        ranges = omabox.subordinate_ranges([listing, listing.with_name("missing")])
        self.assertEqual(ranges, [(0x70000000, 0x70010000)])
        picks = iter([5, 65536 + 7, 65536 + 9])
        with mock.patch.object(omabox.pwd, "getpwuid", lambda n: n == 0x70010007 and object() or (_ for _ in ()).throw(KeyError(n))):
            self.assertEqual(omabox.unused_id(lambda limit: next(picks), ranges), 0x70010009)
        with self.assertRaises(RuntimeError):
            omabox.unused_id(lambda limit: 0, ranges)

    def test_a_taken_port_is_retried_on_another(self):
        ports = iter([40001, 40002])
        tries = []

        def run(argv, **kwargs):
            if argv[:2] == ["podman", "run"]:
                tries.append(argv[argv.index("-p") + 1])
                busy = len(tries) == 1
                return subprocess.CompletedProcess(argv, 126 if busy else 0, "",
                                                   "Listen failed: Address already in use" if busy else "")
            return subprocess.CompletedProcess(argv, 0, "", "")

        token_path = Path(tempfile.mkdtemp()) / "x-token"
        token_path.write_text("secret-token\n")
        with mock.patch.object(omabox, "free_port", lambda: next(ports)):
            with omabox.rsshub_session(True, run=run, wait=lambda: None, check=lambda: None, token_path=token_path,
                                       engine="podman"):
                self.assertEqual(omabox.RSSHUB_LIVE_PORT, 40002)
        self.assertEqual(tries, ["127.0.0.1:40001:1200", "127.0.0.1:40002:1200"])

    def test_container_is_locked_down_and_keyed(self):
        calls, env = self.run_session()
        (start,) = [argv for argv in calls if argv[:2] == ["podman", "run"]]
        for flag in ("--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--memory=512m"):
            self.assertIn(flag, start)
        self.assertEqual(start[start.index("--user") + 1], "65534:65534")
        self.assertEqual(start[start.index("-p") + 1], f"127.0.0.1:{env['live'][0]}:1200")
        self.assertIn("@sha256:", start[-1])
        self.assertEqual(start[start.index("--timeout") + 1], str(omabox.RSSHUB_MAX_SECONDS))
        self.assertRegex(env["text"], r"(?m)^ACCESS_KEY=[\w-]{20,}$")
        self.assertIn("DEBUG_INFO=false", env["text"])
        self.assertEqual(omabox.RSSHUB_KEY, "")

    def test_requests_go_to_the_running_container_with_its_key(self):
        route = f"{omabox.RSSHUB_BASE}/twitter/user/rowanvale?format=json"
        with self.assertRaises(RuntimeError):
            omabox.rsshub_keyed(route)
        with mock.patch.object(omabox, "RSSHUB_KEY", "k3y"), mock.patch.object(omabox, "RSSHUB_LIVE_PORT", 40001):
            code = omabox.hashlib.md5(b"/twitter/user/rowanvalek3y").hexdigest()
            self.assertEqual(omabox.rsshub_keyed(route), f"http://127.0.0.1:40001/twitter/user/rowanvale?format=json&code={code}")
            code = omabox.hashlib.md5(b"/twitter/user/a/includeRts=falsek3y").hexdigest()
            self.assertEqual(omabox.rsshub_keyed(f"{omabox.RSSHUB_BASE}/twitter/user/a/includeRts=false"),
                             f"http://127.0.0.1:40001/twitter/user/a/includeRts=false?code={code}")
            self.assertNotIn("k3y", omabox.rsshub_keyed(route))
            self.assertEqual(omabox.rsshub_keyed("https://blog.example/feed"), "https://blog.example/feed")

    def test_rsshub_requests_never_go_through_a_proxy(self):
        rsshub, asked = recording_server(self, body=b"{}")
        proxy, proxied = recording_server(self, status=502)
        route = f"{omabox.RSSHUB_BASE}/twitter/user/rowanvale?format=json"
        with mock.patch.dict(omabox.os.environ, {"http_proxy": f"http://127.0.0.1:{proxy}", "no_proxy": ""}), \
                mock.patch.object(urllib.request, "_opener", None), \
                mock.patch.object(omabox, "RSSHUB_KEY", "k3y"), mock.patch.object(omabox, "RSSHUB_LIVE_PORT", rsshub):
            omabox.download(route)
            omabox.download_feed(route)
            self.assertTrue(omabox.rsshub_up())
        self.assertEqual(proxied, [])
        self.assertEqual(len(asked), 3)

    def test_token_file_readable_by_others_is_tightened(self):
        token_path = Path(tempfile.mkdtemp()) / "x-token"
        token_path.write_text("secret-token\n")
        token_path.chmod(0o644)
        with omabox.rsshub_session(True, run=lambda argv, **kw: type("R", (), {"returncode": 0, "stderr": ""})(),
                                   wait=lambda: None, check=lambda: None, token_path=token_path, engine="podman"):
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
                with omabox.rsshub_session(True, run=lambda *a, **k: None, wait=lambda: None, check=lambda: None):
                    pass
        finally:
            omabox.container_engine = real
        self.assertIn("podman or docker", str(caught.exception))

    def test_failed_start_reports_without_token(self):
        with self.assertRaises(RuntimeError) as caught:
            self.run_session(start_code=125)
        self.assertNotIn("secret-token", str(caught.exception))

    def test_without_a_runtime_dir_files_stay_in_the_private_state_folder(self):
        state = Path(tempfile.mkdtemp()) / "state" / "items.json"
        shared = Path(tempfile.mkdtemp())
        shared.chmod(0o1777)
        with mock.patch.dict(omabox.os.environ, {"TMPDIR": str(shared)}), mock.patch.object(omabox, "STATE_PATH", state):
            del omabox.os.environ["XDG_RUNTIME_DIR"]
            self.assertEqual(omabox.runtime_dir(), state.parent)
            self.assertEqual(state.parent.stat().st_mode & 0o777, 0o700)
            # files another user planted there under the old fixed names change nothing
            (shared / omabox.RSSHUB_MARKER).write_text("podman\n")
            (shared / "omabox-rsshub.lock").mkdir()
            omabox.stop_stale_rsshub(lambda *a, **k: self.fail("nothing to stop"))
        self.assertFalse((state.parent / omabox.RSSHUB_MARKER).exists())

    def test_fetch_goes_on_when_the_stale_container_check_fails(self):
        args = argparse.Namespace(offline=True, all=False, only=None, notify=False, retry=False)
        with mock.patch.object(omabox, "stop_stale_rsshub", side_effect=PermissionError("lock")), \
                mock.patch.object(omabox, "run_fetch", lambda args, state=None: "fetched"), \
                mock.patch.object(omabox, "fetch_lock", lambda: contextlib.nullcontext(True)):
            self.assertEqual(omabox.cmd_fetch(args), "fetched")

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
        fetched = []
        state = omabox.load_state(Path(tempfile.mkdtemp()) / "missing.json")
        state["errors"]["B"] = "URLError: timed out"

        def gather(snapshot, source, stamp):
            fetched.append(source["name"])
            error = omabox.X_TOKEN_ERROR if source["name"] == "A" else ""
            return omabox.Gathered(source["name"], source["url"], stamp, error, store=lambda state: 0)

        results = omabox.gather_via_rsshub(state, sources, "t", gather)
        self.assertEqual(fetched, ["A", "Repo"])
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual([result(state) for result in results], [0, 0, 0])
        self.assertEqual(state["errors"]["B"], omabox.X_TOKEN_ERROR)

    def test_a_fetch_replaces_the_token_error_of_the_last_run(self):
        state = omabox.load_state(Path(tempfile.mkdtemp()) / "missing.json")
        state["errors"]["A"] = omabox.X_TOKEN_ERROR
        empty = b'{"title": "Twitter @rowanvale", "home_page_url": "https://x.com/rowanvale", "items": []}'
        sources = [{"name": "A", "url": self.ROUTE, "icon": "*"}, {"name": "B", "url": self.ROUTE, "icon": "*"}]
        fetched = []

        def gather(snapshot, source, stamp):
            fetched.append(source["name"])
            return omabox.gather_source(snapshot, source, stamp, get=lambda url, cached: (empty, {}))

        results = omabox.gather_via_rsshub(state, sources, "t", gather)
        with contextlib.redirect_stdout(io.StringIO()):
            for result in results:
                result(state)
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
        self.assertIn("2 X sources waiting.", body)

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


class FeedRedirectTest(unittest.TestCase):
    """127.0.0.2 stands in for a public feed host, 127.0.0.1 for the LAN."""

    def setUp(self):
        real = omabox.public_address
        patcher = mock.patch.object(omabox, "public_address", lambda address: address == "127.0.0.2" or (
            real(address) if not address.startswith("127.") else False))
        patcher.start()
        self.addCleanup(patcher.stop)
        proxies = mock.patch.dict(omabox.os.environ, {"no_proxy": "*"})
        proxies.start()
        self.addCleanup(proxies.stop)
        self.lan, self.lan_seen = recording_server(self, body=RSS_FEED)

    def feed_host(self, location):
        seen = []

        class Feed(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append(self.path)
                self.send_response(302)
                self.send_header("Location", location)
                self.end_headers()

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.2", 0), Feed)
        threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.2:{server.server_port}"

    def test_a_public_feed_cannot_redirect_into_the_lan(self):
        base = self.feed_host(f"http://127.0.0.1:{self.lan}/reboot")
        for get in (omabox.download_feed, omabox.download):
            with self.assertRaises((ValueError, OSError)):
                get(base + "/feed.xml")
        self.assertEqual(self.lan_seen, [])

    def test_a_feed_on_the_lan_keeps_working_and_may_redirect_there(self):
        lan = f"http://127.0.0.1:{self.lan}"
        self.assertEqual(omabox.download_feed(lan + "/feed.xml")[0], RSS_FEED)
        other, _ = recording_server(self, status=302, headers={"Location": lan + "/moved.xml"})
        self.assertEqual(omabox.download(f"http://127.0.0.1:{other}/feed.xml")[1], RSS_FEED)
        self.assertEqual(self.lan_seen, ["/feed.xml", "/moved.xml"])

    def resolving(self, answers):
        real = socket.getaddrinfo

        def resolve(host, port, *args, **kwargs):
            if host not in answers:
                return real(host, port, *args, **kwargs)
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (answers[host], port or 0))]

        return mock.patch.object(omabox.socket, "getaddrinfo", resolve)

    def test_a_public_name_answering_a_local_address_stays_public(self):
        source = {"name": "Tides", "url": f"http://feeds.example:{self.lan}/feed.xml", "cadence": "daily"}
        with self.resolving({"feeds.example": "127.0.0.1"}):
            self.assertIs(omabox.feed_opener(source["url"]), omabox.PUBLIC_OPENER)
            gathered = omabox.gather_source({"items": [], "http": {}, "icons": {}, "profiles": {}}, source, omabox.now_iso())
        self.assertIn("non-public address refused", gathered.error)
        self.assertEqual(self.lan_seen, [])

    def test_a_local_source_by_name_dials_local_addresses_only(self):
        source = {"name": "Nas", "url": f"http://nas.example.net:{self.lan}/feed.xml", "cadence": "daily", "lan": True}
        snapshot = {"items": [], "http": {}, "icons": {}, "profiles": {}}
        with self.resolving({"nas.example.net": "127.0.0.1"}), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(omabox.gather_source(snapshot, source, omabox.now_iso()).error, "")
        self.assertEqual(self.lan_seen, ["/feed.xml"])
        with self.resolving({"nas.example.net": "127.0.0.2"}):
            self.assertIn("public address refused", omabox.gather_source(snapshot, source, omabox.now_iso()).error)
        self.assertEqual(self.lan_seen, ["/feed.xml"])

    def test_local_urls_are_known_without_a_lookup(self):
        shared = ipaddress.ip_network((0x64400000, 10))  # RFC 6598 shared address space
        local = ["http://192.168.1.20/feed", "http://[::1]:8080/", "http://localhost/", "http://nas:8080/rss",
                 f"http://{shared[7]}/", *(f"http://reader{suffix}./feed" for suffix in omabox.LOCAL_NAME_SUFFIXES)]
        for url in local:
            self.assertTrue(omabox.local_url(url), url)
        for url in ("https://feeds.example/rss", "https://93.184.216.34/", "https://local.example/", "file:///x"):
            self.assertFalse(omabox.local_url(url), url)

    def test_adding_a_feed_by_a_local_name_marks_it(self):
        root = Path(tempfile.mkdtemp())
        for name, path in (("CONFIG_PATH", root / "sources.toml"), ("STATE_PATH", root / "items.json"),
                           ("DISCOVER_DIR", root / "discover"), ("IMAGE_DIR", root / "images"), ("ICON_DIR", root / "icons")):
            patcher = mock.patch.object(omabox, name, path)
            patcher.start()
            self.addCleanup(patcher.stop)
        omabox.save_sources([])
        with self.resolving({"nas.example.net": "127.0.0.1"}), contextlib.redirect_stdout(io.StringIO()):
            omabox.cmd_add(argparse.Namespace(url=f"http://nas.example.net:{self.lan}/feed.xml", name="Nas", cadence="daily"))
            omabox.cmd_add(argparse.Namespace(url=f"http://127.0.0.1:{self.lan}/other.xml", name="Here", cadence="daily"))
        self.assertEqual([source.get("lan") for source in omabox.load_sources()], [True, None])
        self.assertEqual(self.lan_seen, ["/feed.xml", "/other.xml"])

    def test_only_web_addresses(self):
        path = Path(tempfile.mkdtemp()) / "feed.xml"
        path.write_bytes(RSS_FEED)
        for get in (omabox.download_feed, omabox.download):
            with self.assertRaises(ValueError):
                get(path.as_uri())
        for target in (path.as_uri(), "ftp://127.0.0.1/feed.xml"):
            lan_to_file, _ = recording_server(self, status=302, headers={"Location": target})
            with self.assertRaises((ValueError, OSError)):
                omabox.download_feed(f"http://127.0.0.1:{lan_to_file}/feed.xml")


class DowngradeTest(unittest.TestCase):
    def test_no_opener_follows_https_down_to_http(self):
        request = urllib.request.Request("https://img.example/v.mp4")
        with mock.patch.object(omabox, "public_host", lambda url: True):
            for opener in (omabox.PUBLIC_OPENER, omabox.LAN_OPENER):
                (handler,) = [h for h in opener.handlers if isinstance(h, urllib.request.HTTPRedirectHandler)]
                self.assertIsInstance(handler, omabox.WebRedirects)
                with self.assertRaises(ValueError):
                    handler.redirect_request(request, None, 302, "Found", {}, "http://img.example/v.mp4")
                followed = handler.redirect_request(request, None, 302, "Found", {}, "https://cdn.example/v.mp4")
                self.assertEqual(followed.full_url, "https://cdn.example/v.mp4")
                plain = urllib.request.Request("http://img.example/v.mp4")
                self.assertEqual(handler.redirect_request(plain, None, 302, "Found", {}, "https://img.example/v.mp4")
                                 .full_url, "https://img.example/v.mp4")


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


class RedditPaceTest(unittest.TestCase):
    LIMIT = {"x-ratelimit-remaining": "0.0", "x-ratelimit-reset": "30"}

    def setUp(self):
        class Clock:
            now = 1000.0

            def monotonic(self):
                return self.now

            def sleep(self, seconds):
                self.now += seconds

            def __getattr__(self, name):
                return getattr(time, name)

        self.clock = Clock()
        for patcher in (mock.patch.object(omabox, "time", self.clock),
                        mock.patch.dict(omabox.REDDIT_PACE, {"free_at": 0.0})):
            patcher.start()
            self.addCleanup(patcher.stop)

    def opener(self, *answers):
        """answers: (status, headers) for each request in turn; seen: the clock at each request."""
        answers, seen, clock = list(answers), [], self.clock

        class Response:
            def __init__(self, headers):
                self.headers, self.left = headers, RSS_FEED

            def read(self, amount=-1):
                chunk, self.left = self.left, b""
                return chunk

            def geturl(self):
                return "https://www.reddit.com/r/a/.rss"

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def open_(request, timeout):
            status, headers = answers.pop(0)
            seen.append(clock.now)
            if status != 200:
                raise urllib.error.HTTPError(request.full_url, status, "status", headers, None)
            return Response(headers)

        return open_, seen

    def test_subreddits_in_one_run_wait_for_reddits_next_minute(self):
        opener, seen = self.opener((200, self.LIMIT), (200, {**self.LIMIT, "x-ratelimit-reset": "59"}), (200, {}))
        omabox.download("https://www.reddit.com/r/a/.rss", opener=opener)
        self.assertEqual(omabox.download_feed("https://old.reddit.com/r/b/.rss", None, opener)[0], RSS_FEED)
        omabox.download_feed("https://www.reddit.com/r/c/.rss", None, opener)
        self.assertEqual(seen, [1000.0, 1031.0, 1091.0])

    def test_a_429_from_another_request_is_waited_out_once(self):
        opener, seen = self.opener((429, {**self.LIMIT, "x-ratelimit-reset": "12"}), (200, self.LIMIT))
        self.assertEqual(omabox.download_feed("https://www.reddit.com/r/a/.rss", None, opener)[0], RSS_FEED)
        self.assertEqual(seen, [1000.0, 1013.0])
        opener, seen = self.opener((429, {}), (429, {}))
        with self.assertRaises(urllib.error.HTTPError) as caught:
            omabox.download_feed("https://www.reddit.com/r/b/.rss", None, opener)
        caught.exception.close()
        self.assertEqual(seen, [1044.0, 1105.0])

    def test_other_sites_are_not_paced(self):
        opener, seen = self.opener((200, self.LIMIT), (200, self.LIMIT), (404, self.LIMIT))
        omabox.download_feed("https://a.example/feed", None, opener)
        omabox.download_feed("https://notreddit.com/r/a/.rss", None, opener)
        with self.assertRaises(urllib.error.HTTPError) as caught:
            omabox.download_feed("https://a.example/feed", None, opener)
        caught.exception.close()
        self.assertEqual(seen, [1000.0, 1000.0, 1000.0])


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

        def gather(snapshot, source, stamp):
            return omabox.Gathered(source["name"], source["url"], stamp, omabox.X_TOKEN_ERROR)

        results = omabox.gather_via_rsshub(state, [{"name": "A", "url": f"{base}/twitter/user/a"},
                                                   {"name": "B", "url": f"{base}/twitter/user/b"}], "t", gather)
        with contextlib.redirect_stderr(io.StringIO()):
            results[1](state)
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
                     lambda entry: omabox.ImageFetcher(entry["link"], lambda url, limit: jpeg(48, 48)
                                                       if "/profile_images/" in url else jpeg(800, 400), directory),
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


class ViewerTest(unittest.TestCase):
    PATHS = ["/c/a.png", "/c/b.jpg", "/c/c.gif"]
    URLS = ["https://video.twimg.com/a.mp4", "https://video.twimg.com/b.mp4"]

    def setUp(self):
        self.runtime = Path(tempfile.mkdtemp())
        patcher = mock.patch.dict(omabox.os.environ, {"XDG_RUNTIME_DIR": str(self.runtime)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def play(self, urls, start=0, window_after=1, exits=None, window_gone_after=None, players=None, direct_players=None):
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

        def mpv_only(urls, start, ipc=None):
            return ["mpv", f"--playlist-start={start}", "--"] + urls

        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.dict(omabox.os.environ, {"http_proxy": "http://192.0.2.1:3128"}):
            omabox.cmd_play(argparse.Namespace(urls=urls, start=start), run, windows, poll_every=0, wait_seconds=5,
                            relay=relay, focus=lambda address: launched.append("focus " + address),
                            players=players or mpv_only, direct_players=direct_players or mpv_only)
        self.looks = len(looks)
        return launched, out.getvalue()

    def test_play_starts_the_player_on_the_relay_at_the_clicked_video_and_waits_for_it(self):
        launched, out = self.play(self.URLS, start=1, window_after=3)
        self.assertEqual(launched, [["mpv", "--playlist-start=1", "--", "http://127.0.0.1:9/t/0.mp4",
                                     "http://127.0.0.1:9/t/1.mp4"], "focus 0xplayer", "waited"])
        self.assertNotIn("http_proxy", self.env)
        self.assertEqual(out, "opened\n")

    def test_mpv_gets_its_files_over_a_socket_not_in_argv(self):
        received = {}

        def run(argv, env=None, pass_fds=(), **kwargs):
            received["argv"], received["fd"] = argv, os.dup(pass_fds[0])

            class Player:
                def poll(self):
                    return None

                def wait(self):
                    pass

            return Player()

        with self.installed("mpv"), mock.patch.object(omabox, "default_desktop_file", lambda mime: None), \
                contextlib.redirect_stdout(io.StringIO()):
            omabox.cmd_play(argparse.Namespace(urls=self.URLS, start=1), run, lambda: None, poll_every=0,
                            relay=lambda urls: [f"http://127.0.0.1:9/t0k3n/{i}.mp4" for i in range(len(urls))],
                            focus=lambda address: None)
        argv = received["argv"]
        self.assertFalse(any("127.0.0.1" in arg or "example" in arg for arg in argv), argv)
        self.assertEqual(argv[:5], ["mpv", "--playlist-start=1", "--tls-verify=yes", "--ytdl=no", "--access-references=no"])
        self.assertIn("--idle=once", argv)
        self.assertRegex(argv[-1], r"^--input-ipc-client=fd://\d+$")
        with socket.socket(fileno=received["fd"]) as sock:
            lines = sock.recv(65536).decode().splitlines()
        self.assertEqual([json.loads(line)["command"] for line in lines],
                         [["loadfile", "http://127.0.0.1:9/t0k3n/0.mp4", "append"],
                          ["loadfile", "http://127.0.0.1:9/t0k3n/1.mp4", "append-play"]])
        with self.installed("mpv", "yt-dlp"):
            direct = omabox.direct_player_argv(["ytdl://b-_a7ghi6-upq3_Cr-gRpg"], 0, ipc=7)
        self.assertEqual(direct, ["mpv", "--playlist-start=0", "--tls-verify=yes", f"--script-opts-append=ytdl_hook-ytdl_path="
                                  f"{omabox.YTDL_WRAPPER}", "--script-opts-append=ytdl_hook-try_ytdl_first=no",
                                  "--script-opts-append=ytdl_hook-exclude=.", "--idle=once", "--input-ipc-client=fd://7"])

    @unittest.skipUnless(omabox.shutil.which("mpv") and omabox.shutil.which("ffmpeg"), "needs mpv and ffmpeg")
    def test_mpv_starts_at_the_clicked_video_with_the_others_around_it(self):
        root = Path(tempfile.mkdtemp())
        subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=1:size=64x48:rate=5",
                        "-pix_fmt", "yuv420p", str(root / "clip.mp4")], check=True, timeout=60)
        (root / "mpv").mkdir()
        port, _ = recording_server(self, body=lambda path: (root / "clip.mp4").read_bytes(), headers={"Content-Type": "video/mp4"})
        plain = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for start in (0, 1, 2):
            log = root / f"mpv-{start}.log"
            (root / "mpv" / "mpv.conf").write_text(f"vo=null\nao=null\nframes=2\nlog-file={log}\n")
            with mock.patch.dict(omabox.os.environ, {"MPV_HOME": str(root / "mpv")}), \
                    mock.patch.object(omabox, "default_desktop_file", lambda mime: None), \
                    contextlib.redirect_stdout(io.StringIO()):
                omabox.cmd_play(argparse.Namespace(urls=self.URLS + ["https://video.twimg.com/c.mp4"], start=start),
                                windows=lambda: None, focus=lambda address: None,
                                relay=lambda urls: omabox.start_relay([f"http://127.0.0.1:{port}/{i}.mp4" for i in range(3)], plain))
            played = re.findall(r"Playing: http://127\.0\.0\.1:\d+/[\w-]+/(\d)\.mp4", log.read_text())
            self.assertEqual(played, [str(index) for index in range(start, 3)], start)

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

    def test_youtube_videos_go_to_mpv_as_watch_pages_with_the_proxy_kept(self):
        urls = ["https://www.youtube.com/watch?v=Zq3vKe8TbWo", "https://www.youtube.com/shorts/Ab3vKe8TbW_"]
        seen = {}

        def mpv(files, start, ipc=None):
            seen.update({file: (self.runtime / "omabox-ytdl" / file[7:]).read_text() for file in files})
            return ["mpv", f"--playlist-start={start}", "--"] + files

        launched, out = self.play(urls, start=1, window_after=3, direct_players=mpv)
        self.assertTrue(all(arg.startswith(("mpv", "--")) or re.fullmatch(r"ytdl://[\w-]{22}", arg) for arg in launched[0]),
                        launched[0])
        self.assertEqual(list(seen.values()), urls)
        self.assertEqual(list(seen), launched[0][3:])
        self.assertEqual(list((self.runtime / "omabox-ytdl").iterdir()), [])
        self.assertEqual(self.env["OMABOX_YTDL_TOKENS"], str(self.runtime / "omabox-ytdl"))
        self.assertEqual(self.env["http_proxy"], "http://192.0.2.1:3128")
        with self.assertRaises(SystemExit) as caught:
            self.play(urls, direct_players=lambda urls, start, ipc=None: None)
        self.assertIn("need mpv (and yt-dlp for YouTube)", str(caught.exception.code))
        reddit = ["https://v.redd.it/ab12cd/DASHPlaylist.mpd"]
        with self.installed("mpv"):
            self.assertIsNone(omabox.direct_player_argv(urls, 0))
            self.assertIsNone(omabox.direct_player_argv(["ytdl://b-_a7ghi6-upq3_Cr-gRpg"], 0))
            self.assertEqual(omabox.direct_player_argv(reddit, 0), ["mpv", "--playlist-start=0", "--tls-verify=yes",
                                                                    "--ytdl=no", "--"] + reddit)
        with self.installed("mpv", "yt-dlp"):
            self.assertEqual(omabox.direct_player_argv(["ytdl://b-_a7ghi6-upq3_Cr-gRpg"], 0)[:4],
                             ["mpv", "--playlist-start=0", "--tls-verify=yes",
                              f"--script-opts-append=ytdl_hook-ytdl_path={omabox.YTDL_WRAPPER}"])
            self.assertIn("--ytdl=no", omabox.direct_player_argv(urls, 0))
        self.assertTrue(omabox.direct_video(reddit[0]))
        self.assertTrue(omabox.direct_video("https://video.bsky.app/watch/did%3Aplc%3Aab12/bafkre1/playlist.m3u8"))
        self.assertFalse(omabox.direct_video("https://video.bsky.app.example/watch/did%3Aplc%3Aab12/bafkre1/playlist.m3u8"))
        self.assertFalse(omabox.direct_video("https://v.redd.it.example/ab12cd/DASHPlaylist.mpd"))
        self.assertFalse(omabox.youtube_video("https://www.youtube.com/channel/UC1234567890123456789012"))

    def test_play_without_a_player_says_so(self):
        with self.assertRaises(SystemExit) as caught:
            self.play(self.URLS, players=lambda urls, start, ipc=None: None)
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

    def test_the_ytdl_wrapper_hands_yt_dlp_the_address_on_stdin_only(self):
        root = Path(tempfile.mkdtemp())
        (root / "bin").mkdir()
        fake = root / "bin" / "yt-dlp"
        fake.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" > {root}/argv\ncat > {root}/stdin\necho "{{}}"\n')
        fake.chmod(0o755)
        files, made = omabox.ytdl_tokens(["https://www.youtube.com/watch?v=Zq3vKe8TbWo", "https://v.redd.it/ab/DASHPlaylist.mpd"],
                                         root / "tokens")
        self.assertEqual(files[1], "https://v.redd.it/ab/DASHPlaylist.mpd")
        self.assertEqual((root / "tokens").stat().st_mode & 0o777, 0o700)
        self.assertEqual(made[0].stat().st_mode & 0o777, 0o600)
        env = {"PATH": f"{root / 'bin'}:/usr/bin", "OMABOX_YTDL_TOKENS": str(root / "tokens")}
        hook = [str(omabox.YTDL_WRAPPER), "--no-warnings", "-J", "--format", "best", "--no-playlist", "--"]
        ran = subprocess.run(hook + [files[0][len("ytdl://"):]], env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual((ran.returncode, ran.stdout), (0, "{}\n"), ran.stderr)
        self.assertEqual((root / "argv").read_text().split(), ["--no-warnings", "-J", "--format", "best", "--no-playlist",
                                                               "--batch-file", "-"])
        self.assertEqual((root / "stdin").read_text(), "https://www.youtube.com/watch?v=Zq3vKe8TbWo\n")
        (root / "argv").unlink()
        for last in (files[1], "ytdl://" + made[0].name, "A" * 22, "../tokens/" + made[0].name):
            ran = subprocess.run(hook + [last], env=env, capture_output=True, text=True, timeout=30)
            self.assertNotEqual(ran.returncode, 0, last)
        self.assertFalse((root / "argv").exists())

    def test_default_mpv_keeps_the_post_order(self):
        with self.installed("mpv"):
            argv = omabox.player_argv(["u0", "u1"], 1, self.desktop("mpv --player-operation-mode=pseudo-gui -- %U"))
        self.assertEqual(argv, ["mpv", "--playlist-start=1", "--tls-verify=yes", "--ytdl=no", "--access-references=no", "--",
                                "u0", "u1"])

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

    def upstream(self, body, content_type="video/mp4"):
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
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(last - first + 1))
                self.send_header("Set-Cookie", "tracker=1")
                if ranged:
                    self.send_header("Content-Range", f"bytes {first}-{last}/{len(body)}")
                self.end_headers()
                self.wfile.write(body[first:last + 1])

            def log_message(self, format, *args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Host)
        threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
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
        body = b"\x00\x00\x00\x18ftypisom" + bytes(range(256)) * 40
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

    def test_relay_passes_media_files_only_never_playlists(self):
        plain = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        lists = (b"#EXTM3U\nhttp://192.0.2.10/lan\n", b"[playlist]\nFile1=http://192.0.2.10/lan\n",
                 b'<?xml version="1.0"?><MPD><BaseURL>http://192.0.2.10/lan</BaseURL></MPD>', b"http://192.0.2.10/lan\n")
        for body in lists:
            local = omabox.start_relay([self.upstream(body * 20) + "/v.mp4"], opener=plain)
            self.assertEqual(self.fetch(local[0])[0], 415, body)
            self.assertEqual(self.fetch(local[0], {"Range": "bytes=40-"})[0], 415, body)
        media = {"mp4": b"\x00\x00\x00\x18ftypisom", "webm": b"\x1a\x45\xdf\xa3", "ogg": b"OggS", "mp3": b"ID3\x04\x00"}
        for name, start in media.items():
            local = omabox.start_relay([self.upstream(start + bytes(400)) + "/v.mp4"], opener=plain)
            self.assertEqual(self.fetch(local[0], {"Range": "bytes=40-"})[:3:2], (206, bytes(len(start) + 360)), name)
            self.assertEqual(self.fetch(local[0])[0], 200, name)
        typed = omabox.start_relay([self.upstream(media["mp4"] + bytes(400), "audio/x-mpegurl") + "/v.mp4"], opener=plain)
        self.assertEqual(self.fetch(typed[0])[0], 415)

    def test_relay_paths_keep_media_suffixes_only(self):
        local = omabox.start_relay(["https://cdn.example/a.MP4", "https://cdn.example/b.m3u", "https://cdn.example/c.pls?x=.mp4",
                                    "https://cdn.example/d"])
        self.assertEqual([url.rsplit("/", 1)[1] for url in local], ["0.mp4", "1", "2", "3"])

    def test_media_heads_need_real_headers(self):
        mpeg = b"\xff\xfb\x90\x64" + bytes(600)
        for head in (b"ID3\x03\x00\x00\x00\x00\x10\x7f", mpeg, b"\xff\xf1\x50\x80", b"\x00\x00\x00\x18ftypisom",
                     (b"\x47" + bytes(187)) * 3):
            self.assertTrue(omabox.media_head(head + bytes(600)), head[:12])
        for head in (b"ID3\n#\nhttp://192.0.2.10/admin\n", b"ID3\x03\x00\x00\x00\x00\x80\x00", b"\xff\xff\xff\xff",
                     b"\xff\xfb\xf0\x00", b"\xff\xe9\x90\x00", b"\x00\x00\x00\x02ftyp", (b"G" + b"a" * 187) * 2 + b"x" * 200):
            self.assertFalse(omabox.media_head(head + b"\nhttp://192.0.2.10/admin\n"), head[:12])

    def test_relay_serves_this_account_only(self):
        plain = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        local = omabox.start_relay([self.upstream(b"\x00\x00\x00\x18ftypisom" + bytes(400)) + "/v.mp4"], opener=plain)
        self.assertEqual(self.fetch(local[0])[0], 200)
        other = os.getuid() + 4242
        with mock.patch.object(omabox.os, "getuid", lambda: other):
            self.assertEqual(self.fetch(local[0])[0], 403)
            self.assertEqual(self.fetch(local[0], {"Range": "bytes=40-"})[0], 403)

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
def reddit_footer(user, target, comments):
    return (f'&#32; submitted by &#32; <a href="https://www.reddit.com/user/{user}"> /u/{user} </a> <br/> '
            f'<span><a href="{target}">[link]</a></span> &#32; <span><a href="{comments}">[comments]</a></span>')


REDDIT_FEED = ("""<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom"><title>lanterns</title>
<entry><id>t3_1ab2</id><title>A guide to wicks</title><updated>2026-09-27T07:00:00+00:00</updated>
<link href="https://www.reddit.com/r/lanterns/comments/1ab2/a_guide/"/><content type="html">"""
               + html.escape(reddit_footer("wickmaker", "https://lantern.example/guide",
                                           "https://www.reddit.com/r/lanterns/comments/1ab2/a_guide/"))
               + """</content></entry>
<entry><id>t3_1ab3</id><title>Which wick?</title><updated>2026-09-27T06:00:00+00:00</updated>
<link href="https://www.reddit.com/r/lanterns/comments/1ab3/which_wick/"/><content type="html">"""
               + html.escape('<!-- SC_OFF --><div class="md"><p>Which wick lasts longest?</p></div><!-- SC_ON --> '
                             + reddit_footer("emberfield", "https://www.reddit.com/r/lanterns/comments/1ab3/which_wick/",
                                             "https://www.reddit.com/r/lanterns/comments/1ab3/which_wick/"))
               + "</content></entry></feed>").encode()


def reddit_comment(cid, author, body):
    return (f'<entry><author><name>/u/{author}</name></author><id>t1_{cid}</id>'
            f'<link href="https://www.reddit.com/r/lanterns/comments/1ab3/which_wick/{cid}/"/>'
            f'<updated>2026-09-21T14:13:20+00:00</updated><title>/u/{author} on Which wick?</title>'
            f'<content type="html">{html.escape(f"<div class=\"md\"><p>{body}</p></div>")}</content></entry>')


REDDIT_COMMENTS = ('<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom">'
                   '<entry><author><name>/u/emberfield</name></author><id>t3_1ab3</id>'
                   '<link href="https://www.reddit.com/r/lanterns/comments/1ab3/which_wick/"/>'
                   '<updated>2026-09-21T12:00:00+00:00</updated><title>Which wick?</title>'
                   '<content type="html">&lt;p&gt;Which wick lasts longest?&lt;/p&gt;</content></entry>'
                   + reddit_comment("c0", "AutoModerator", "Please read the rules.")
                   + reddit_comment("c1", "wickmaker", 'Cotton, &amp; braided, see <a href="/r/candles">r/candles</a>.')
                   + reddit_comment("c2", "emberfield", "Thanks all!")
                   + reddit_comment("c4", "glowworm", "Hemp for me.")
                   + "</feed>").encode()


def bluesky_reply(rkey, handle, text, replies=(), kind="app.bsky.feed.defs#threadViewPost"):
    return {"$type": kind, "post": {"uri": f"at://did:plc:{handle}/app.bsky.feed.post/{rkey}",
                                    "author": {"handle": f"{handle}.bsky.example", "displayName": handle.title(),
                                               "avatar": f"https://cdn.bsky.example/img/avatar/plain/{handle}@jpeg"},
                                    "record": {"text": text, "createdAt": "2026-09-27T09:00:00.000Z"}},
            "replies": list(replies)}


BLUESKY_THREAD = json.dumps({"thread": {"$type": "app.bsky.feed.defs#threadViewPost",
                                        "post": {"author": {"handle": "lantern.bsky.example"}}, "replies": [
    bluesky_reply("r1", "wick", "Lovely glow", [bluesky_reply("r2", "lantern", "Thanks!", [
        bluesky_reply("r3", "wick", "Any time", [bluesky_reply("r4", "ember", "too deep")])])]),
    {"$type": "app.bsky.feed.defs#blockedPost", "uri": "at://did:plc:x/app.bsky.feed.post/r5"},
    bluesky_reply("r6", "ember", "Which oil?"),
]}})


def mastodon_status(sid, parent, acct, content, **extra):
    return {"id": sid, "in_reply_to_id": parent, "url": f"https://social.example/@{acct}/{sid}",
            "created_at": "2026-09-27T09:00:00.000Z", "content": content, "spoiler_text": "", "media_attachments": [],
            "account": {"acct": acct, "username": acct, "display_name": acct.title(),
                        "avatar_static": f"https://social.example/avatars/{acct}.png"}, **extra}


MENTION = '<span class="h-card" translate="no"><a href="https://social.example/@lantern" class="u-url mention">@<span>lantern</span></a></span>'
MASTODON_CONTEXT = json.dumps({"ancestors": [], "descendants": [
    mastodon_status("11", "10", "wick", f"<p>{MENTION} Lovely glow</p>"),
    mastodon_status("12", "11", "lantern", f"<p>{MENTION} Thanks!</p>",
                    media_attachments=[{"type": "image", "url": "https://social.example/m/1.png", "description": "a lamp"}]),
    mastodon_status("13", "10", "ember@other.example", "<p>Which oil?</p>", spoiler_text="Oil talk"),
    mastodon_status("14", "99", "stray", "<p>not in this thread</p>"),
]})


def hn_comment(cid, author, text, children=()):
    return {"id": cid, "author": author, "text": text, "created_at": "2026-09-27T09:00:00.000Z", "children": list(children)}


HN_ITEM = json.dumps({"id": 4100, "author": "lampwright", "title": "Show HN: Lantern groups", "children": [
    hn_comment(4101, "wick", "<p>Oldest one</p>", [hn_comment(4102, "lampwright", "Thanks!", [
        hn_comment(4103, "wick", "Sure", [hn_comment(4104, "ember", "too deep")])])]),
    hn_comment(4105, None, None, [hn_comment(4106, "ember", "under a deleted one")]),
    hn_comment(4107, "glow", "Ranked first by HN"),
    hn_comment(4108, "late", "Not ranked yet"),
]})


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
            {"id": "reddit", "source": "r/lanterns", "title": "Which wick?", "html": "",
             "link": "https://www.reddit.com/r/lanterns/comments/1ab3/which_wick/", "published": day, "read": False},
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
        for iid, text in (("blog", "only X, Reddit, Hacker News, Bluesky and Mastodon posts"), ("nope", "no post nope")):
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

    def test_reddit_comments_thread_under_their_top_comment(self):
        self.assertEqual(omabox.reddit_post_ref("https://old.reddit.com/r/lanterns/comments/1ab3/which_wick/"),
                         ("lanterns", "1ab3"))
        self.assertIsNone(omabox.reddit_post_ref("https://www.reddit.com/r/lanterns/"))
        author, threads = omabox.parse_reddit_comments(REDDIT_COMMENTS)
        self.assertEqual(author, "emberfield")
        self.assertEqual([[r["id"] for r in thread] for thread in threads], [["c1"], ["c2"], ["c4"]])
        self.assertEqual(threads[0][0]["published"], "2026-09-21T14:13:20Z")
        markup = omabox.replies_markup(threads, author, "2026-09-27T08:00:00Z", site="Reddit")
        self.assertIn('<span class="count">3</span>', markup)
        self.assertIn("Top comments on Reddit, best first", markup)
        self.assertEqual(markup.count('class="opcomment"'), 1)
        self.assertIn('<a href="https://www.reddit.com/r/lanterns/comments/1ab3/which_wick/c4/">', markup)
        self.assertIn("Cotton, &amp; braided", markup)
        self.assertIn('<a href="https://www.reddit.com/r/candles">r/candles</a>', markup)
        self.assertNotIn("@wickmaker", markup)
        self.assertNotIn("rules", markup)
        self.assertIn("No comments on Reddit yet", omabox.replies_markup([], author, "2026-09-27T08:00:00Z", site="Reddit"))

    def test_bluesky_replies_nest_to_three_levels(self):
        self.assertEqual(omabox.bluesky_post_ref("https://bsky.app/profile/lantern.bsky.example/post/3abc"),
                         ("lantern.bsky.example", "3abc"))
        self.assertIsNone(omabox.bluesky_post_ref("https://bsky.app/profile/lantern.bsky.example"))
        author, threads = omabox.parse_bluesky_replies(BLUESKY_THREAD)
        self.assertEqual(author, "lantern.bsky.example")
        self.assertEqual([[r["id"] for r in thread] for thread in threads], [["r1", "r2", "r3"], ["r6"]])
        first = threads[0][0]
        self.assertEqual(first["link"], "https://bsky.app/profile/wick.bsky.example/post/r1")
        self.assertEqual(first["avatar"], "https://cdn.bsky.example/img/avatar_thumbnail/plain/wick@jpeg")
        markup = omabox.replies_markup(threads, author, "2026-09-27T10:00:00Z", site="Bluesky")
        self.assertIn("@wick.bsky.example · ", markup)
        self.assertEqual(markup.count('class="opcomment"'), 1)
        self.assertIn("Replies on Bluesky", markup)

    def test_hacker_news_comments_follow_the_sites_ranking(self):
        discussion = '<p><a href="https://lantern.example">lantern.example</a> · ' \
                     '<a href="https://news.ycombinator.com/item?id=4100">Discussion on Hacker News</a></p>'
        self.assertEqual(omabox.hn_item_ref({"link": "https://lantern.example", "html": discussion}), "4100")
        self.assertEqual(omabox.hn_item_ref({"link": "https://news.ycombinator.com/item?id=4100", "html": ""}), "4100")
        self.assertIsNone(omabox.hn_item_ref({"link": "https://lantern.example", "html": "<p>hi</p>"}))
        author, threads = omabox.parse_hn_comments(HN_ITEM, [4107, 4101, 4105])
        self.assertEqual(author, "lampwright")
        self.assertEqual([[r["id"] for r in thread] for thread in threads], [["4107"], ["4101", "4102", "4103"], ["4108"]])
        self.assertEqual(threads[0][0]["link"], "https://news.ycombinator.com/item?id=4107")
        _, oldest_first = omabox.parse_hn_comments(HN_ITEM)
        self.assertEqual([thread[0]["id"] for thread in oldest_first], ["4101", "4107", "4108"])

    def test_hacker_news_fetch_survives_a_missing_ranking(self):
        state = omabox.load_state()
        state["items"].append({"id": "hn", "source": "Hacker News", "title": "Lantern groups", "published": "2026-09-27T08:00:00Z",
                               "read": False, "link": "https://news.ycombinator.com/item?id=4100", "html": ""})
        omabox.save_state(state)

        def fetch(url, limit):
            self.urls.append(url)
            if "firebaseio" in url:
                raise OSError("down")
            return url, "application/json", HN_ITEM.encode()

        fields = omabox.load_hn_comments(omabox.load_state()["items"][-1], "4100", fetch, self.picture)
        self.assertEqual(self.urls, ["https://hn.algolia.com/api/v1/items/4100",
                                     "https://hacker-news.firebaseio.com/v0/item/4100.json"])
        self.assertEqual(fields["replies_count"], 5)
        # the submitter answered in the oldest thread, so it leads
        self.assertLess(fields["replies_html"].index("Oldest one"), fields["replies_html"].index("Ranked first by HN"))

    def test_author_threads_then_most_liked_come_first(self):
        def thread(handle, likes, *answers):
            return [{"handle": handle, "likes": likes}] + [{"handle": h} for h in answers]

        threads = [thread("a", 1), thread("b", 9), thread("c", 0, "Lantern"), thread("d", 5), thread("e", 2, "x")]
        self.assertEqual([t[0]["handle"] for t in omabox.rank_threads(threads, "lantern")], ["c", "b", "d", "e", "a"])
        no_counts = [[{"handle": h}] for h in "pqr"]
        self.assertEqual(omabox.rank_threads(no_counts, "lantern"), no_counts)

    def test_mastodon_replies_thread_by_parent_and_lose_leading_mentions(self):
        self.assertEqual(omabox.mastodon_post_ref("https://social.example/@lantern/10"), ("social.example", "lantern", "10"))
        self.assertIsNone(omabox.mastodon_post_ref("https://social.example/notice/10"))
        threads = omabox.parse_mastodon_replies(MASTODON_CONTEXT, "10")
        self.assertEqual([[r["id"] for r in thread] for thread in threads], [["11", "12"], ["13"]])
        self.assertEqual(threads[0][0]["html"], "<p>Lovely glow</p>")
        self.assertEqual(threads[0][1]["html"], '<p>Thanks!</p><img src="https://social.example/m/1.png" alt="a lamp">')
        self.assertEqual(threads[1][0]["html"], "<p><b>Oil talk</b></p><p>Which oil?</p>")
        markup = omabox.replies_markup(threads, "lantern", "2026-09-27T10:00:00Z", site="Mastodon")
        self.assertIn("@ember@other.example · ", markup)
        self.assertEqual(markup.count('class="opcomment"'), 1)

    def test_reply_links_are_web_links_only(self):
        for url in ("file:///home/someone/.config/omabox/x-token", "javascript:alert(1)", "omabox-img:x", ""):
            context = json.dumps({"descendants": [{"id": "11", "in_reply_to_id": "10", "url": url, "content": "<p>hi</p>",
                                                   "account": {"acct": "ember"}, "created_at": "2026-09-27T09:00:00Z"}]})
            threads = omabox.parse_mastodon_replies(context.encode(), "10")
            self.assertEqual(threads[0][0]["link"], "")
            markup = omabox.replies_markup(threads, "lantern", "2026-09-27T10:00:00Z", site="Mastodon")
            self.assertNotIn("href", markup.split('class="said"')[0].split('class="who"')[1])
        threads[0][0]["link"] = "file:///etc/passwd"
        self.assertNotIn("file:", omabox.replies_markup(threads, "lantern", "2026-09-27T10:00:00Z", site="Mastodon"))
        threads[0][0]["link"] = "https://social.example/@ember/11"
        self.assertIn('href="https://social.example/@ember/11"',
                      omabox.replies_markup(threads, "lantern", "2026-09-27T10:00:00Z", site="Mastodon"))

    def test_fediverse_fetches_go_to_the_public_apis(self):
        state = omabox.load_state()
        state["items"] += [
            {"id": "sky", "source": "Lantern", "title": "", "html": "", "published": "2026-09-27T08:00:00Z", "read": False,
             "link": "https://bsky.app/profile/lantern.bsky.example/post/3abc", "short": True},
            {"id": "toot", "source": "Lantern", "title": "", "html": "", "published": "2026-09-27T08:00:00Z", "read": False,
             "link": "https://social.example/@lantern/10", "short": True}]
        omabox.save_state(state)
        answers = {"getPostThread": BLUESKY_THREAD, "/context": MASTODON_CONTEXT}

        def fetch(url, limit):
            self.urls.append(url)
            return url, "application/json", next(body for key, body in answers.items() if key in url).encode()

        item = omabox.load_state()["items"][-2]
        sky = omabox.load_fediverse_replies(item, omabox.bluesky_post_ref(item["link"]), None, fetch, self.picture)
        item = omabox.load_state()["items"][-1]
        toot = omabox.load_fediverse_replies(item, None, omabox.mastodon_post_ref(item["link"]), fetch, self.picture)
        self.assertEqual(self.urls, [
            "https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread?uri=at://lantern.bsky.example/app.bsky.feed.post/3abc"
            "&depth=3&parentHeight=0", "https://social.example/api/v1/statuses/10/context"])
        self.assertEqual((sky["replies_count"], toot["replies_count"]), (4, 3))
        self.assertEqual(len(re.findall(r"omabox-avatar:", toot["replies_html"])), 3)
        self.assertEqual(omabox.load_replies("toot"), (toot, True))

    def test_reddit_fetch_reads_the_comments_feed(self):
        def fetch(url):
            self.urls.append(url)
            return url, REDDIT_COMMENTS

        fields, cached = omabox.load_replies("reddit", fetch=fetch, session=self.session, image_fetch=self.picture)
        self.assertFalse(cached)
        self.assertEqual(self.urls, ["https://www.reddit.com/r/lanterns/comments/1ab3/.rss?depth=1"])
        self.assertEqual((fields["replies_count"], self.sessions), (3, 0))
        self.assertEqual(omabox.load_replies("reddit", fetch=fetch, session=self.session), (fields, True))

    def test_json_error(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            omabox.main(["replies", "blog", "--json"])
        self.assertEqual(json.loads(out.getvalue()), {"error": "only X, Reddit, Hacker News, Bluesky and Mastodon posts have comments to show"})


class FetchLockTest(unittest.TestCase):
    FEED = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Tide tables</title><link>https://example.com/1</link><guid>t1</guid><pubDate>Sat, 26 Sep 2026 08:00:00 +0000</pubDate></item>
<item><title>Ferry news</title><link>https://example.com/2</link><guid>t2</guid><pubDate>Fri, 25 Sep 2026 08:00:00 +0000</pubDate></item>
</channel></rss>"""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        names = ("CONFIG_PATH", "STATE_PATH", "IMAGE_DIR", "ICON_DIR")
        saved = {name: getattr(omabox, name) for name in names}
        self.addCleanup(lambda: [setattr(omabox, name, value) for name, value in saved.items()])
        omabox.CONFIG_PATH, omabox.STATE_PATH = self.root / "sources.toml", self.root / "state" / "items.json"
        omabox.IMAGE_DIR, omabox.ICON_DIR = self.root / "images", self.root / "icons"
        runtime = self.root / "run"
        runtime.mkdir(mode=0o700)
        patcher = mock.patch.dict(omabox.os.environ, {"XDG_RUNTIME_DIR": str(runtime)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.during = lambda: None
        self.requests = 0
        test = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                test.requests += 1
                test.during()
                self.send_response(200)
                self.send_header("Content-Type", "application/rss+xml")
                self.end_headers()
                self.wfile.write(test.FEED)

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.url = f"http://127.0.0.1:{server.server_port}/feed.xml"
        omabox.save_sources([{"name": "Tides", "url": self.url, "cadence": "daily", "icon": "*"}])

    def fetch(self):
        args = argparse.Namespace(offline=False, all=True, only=None, notify=False, retry=False)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as errors:
            omabox.cmd_fetch(args)
        return errors.getvalue()

    def test_network_runs_outside_the_state_lock(self):
        free = []

        def during():
            omabox.STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(omabox.STATE_PATH.with_suffix(".lock"), "w") as handle:
                try:
                    omabox.fcntl.flock(handle, omabox.fcntl.LOCK_EX | omabox.fcntl.LOCK_NB)
                    free.append(True)
                except BlockingIOError:
                    free.append(False)
            self.assertTrue(omabox.fetching())

        self.during = during
        self.fetch()
        self.assertEqual(free, [True])
        self.assertEqual(len(omabox.load_state()["items"]), 2)
        self.assertFalse(omabox.fetching())

    def test_sources_changed_during_a_fetch_are_kept_as_they_are_then(self):
        def add_late_source():
            sources = omabox.load_sources()
            omabox.save_sources(sources + [{"name": "Late", "url": "https://example.com/late.xml", "cadence": "daily"}])
            with omabox.locked():
                state = omabox.load_state()
                state["items"].append({"id": "late1", "source": "Late", "title": "Late post", "link": "",
                                       "published": "2026-09-26T08:00:00Z", "read": False, "html": ""})
                state["fetched"]["Late"] = "2026-09-26T08:00:00Z"
                omabox.save_state(state)

        self.during = add_late_source
        self.fetch()
        state = omabox.load_state()
        self.assertEqual(sorted(item["source"] for item in state["items"]), ["Late", "Tides", "Tides"])
        self.assertIn("Late", state["fetched"])

        self.during = lambda: omabox.save_sources([s for s in omabox.load_sources() if s["name"] != "Tides"])
        with omabox.locked():
            state = omabox.load_state()
            state["items"] = [item for item in state["items"] if item["source"] != "Tides"]
            state["fetched"].pop("Tides")
            omabox.save_state(state)
        self.fetch()
        state = omabox.load_state()
        self.assertEqual([item["source"] for item in state["items"]], ["Late"])
        self.assertNotIn("Tides", state["fetched"])

    def tick(self):
        loads, versions = [], []
        real_load, real_version = omabox.load_state, omabox.installed_version
        with mock.patch.object(omabox, "load_state", lambda *a: loads.append(1) or real_load(*a)), \
                mock.patch.object(omabox, "installed_version", lambda c: versions.append(c) or real_version(c)), \
                mock.patch.object(omabox, "archive_notifications", lambda: 0), \
                contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
            omabox.cmd_tick(argparse.Namespace())
        return len(loads), len(versions), int(out.getvalue().split()[-1])

    def test_a_tick_reads_the_state_once_and_runs_version_commands_only_to_deliver(self):
        omabox.save_sources([{"name": "Tides", "url": self.url, "cadence": "daily", "icon": "*",
                              "version_command": "echo v1.2.3"}])
        loads, versions, wait = self.tick()
        self.assertEqual((loads, versions, self.requests), (2, 1, 1))
        self.assertEqual(omabox.load_state()["installed"], {"Tides": "1.2.3"})
        self.assertGreaterEqual(wait, omabox.TICK_MIN_SECONDS)
        loads, versions, wait = self.tick()
        self.assertEqual((loads, versions, self.requests), (1, 0, 1))

    def test_a_second_fetch_skips_while_one_runs(self):
        with omabox.fetch_lock() as alone:
            self.assertTrue(alone)
            self.assertIn("another fetch is running", self.fetch())
        self.assertEqual(self.requests, 0)
        self.assertFalse(omabox.STATE_PATH.exists())


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


QMLTESTRUNNER = next((path for path in ("/usr/lib/qt6/bin/qmltestrunner", omabox.shutil.which("qmltestrunner") or "")
                      if path and Path(path).exists()), None)


class ModelJsTest(unittest.TestCase):
    @unittest.skipUnless(QMLTESTRUNNER, "needs qmltestrunner (qt6-declarative)")
    def test_model_js(self):
        result = subprocess.run([QMLTESTRUNNER, "-input", str(Path(__file__).parent / "tst_model.qml")],
                                env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QML_XHR_ALLOW_FILE_READ": "1"},
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class QmlImportTest(unittest.TestCase):
    def test_theme_colours_use_the_qualified_import(self):
        # QtQuick 6.12 exports its own Color, which shadows the shell's: a bare Color.accent is undefined there.
        root = Path(__file__).resolve().parents[1]
        for path in sorted(root.glob("*.qml")) + sorted(root.glob("tools/**/*.qml")):
            with self.subTest(path.name):
                text = path.read_text()
                self.assertIsNone(re.search(r"(?<![\w.])Color\.", text))
                if "Commons.Color." in text:
                    self.assertIn("import qs.Commons as Commons\n", text)


class TerminalOutputTest(unittest.TestCase):
    EVIL = "a post \x1b]52;c;ZWNobyBwd25lZA==\x07 with \x9b2J words"

    def setUp(self):
        root = Path(tempfile.mkdtemp())
        for name, path in (("STATE_PATH", root / "state" / "items.json"), ("CONFIG_PATH", root / "sources.toml"),
                           ("IMAGE_DIR", root / "images"), ("ICON_DIR", root / "icons")):
            patcher = mock.patch.object(omabox, name, path)
            patcher.start()
            self.addCleanup(patcher.stop)
        omabox.save_sources([{"name": self.EVIL, "url": "https://a.example/feed\x1b[2J", "cadence": "daily"}])
        state = omabox.load_state()
        state["items"].append({"id": "a1", "source": self.EVIL, "title": self.EVIL, "html": "", "read": False,
                               "published": "2026-09-27T09:00:00Z"})
        state["errors"][self.EVIL] = "HTTPError: HTTP Error 500: \x1b]0;title\x07"
        omabox.save_state(state)

    def output(self, command, **args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            command(argparse.Namespace(**args))
        return out.getvalue()

    def test_feed_text_reaches_the_terminal_without_control_characters(self):
        found = {"title": self.EVIL, "url": "https://a.example/\x1b]8;;x\x07", "count": 1,
                 "latest": {"title": self.EVIL, "published": "2026-09-27T09:00:00Z"}}
        with mock.patch.object(omabox, "discover", lambda url: found):
            outputs = [self.output(omabox.cmd_list, all=False), self.output(omabox.cmd_search, query=[], json=False),
                       self.output(omabox.cmd_sources, json=False), self.output(omabox.cmd_discover, url="x", json=False)]
        for out in outputs:
            self.assertIn("a post  ]52;c;ZWNobyBwd25lZA==  with  2J words", out)
            self.assertIsNone(re.search(r"[\x00-\x09\x0b-\x1f\x7f-\x9f]", out), repr(out))
        self.assertEqual(json.loads(self.output(omabox.cmd_search, query=[], json=True))[0]["title"], self.EVIL)


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


class RowsTest(unittest.TestCase):
    def setUp(self):
        saved = omabox.STATE_PATH
        self.addCleanup(setattr, omabox, "STATE_PATH", saved)
        omabox.STATE_PATH = Path(tempfile.mkdtemp()) / "items.json"

    def run_cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            omabox.main(list(argv))
        return out.getvalue()

    def test_rows_are_saved_reported_and_dropped_at_zero(self):
        self.assertEqual(json.loads(self.run_cli("rows", "--json")), {"feed": 0, "notifications": 0})
        self.run_cli("rows", "--feed", "6")
        self.run_cli("rows", "--notifications", "4")
        self.assertEqual(omabox.load_state()["rows"], {"feed": 6, "notifications": 4})
        self.assertEqual(json.loads(self.run_cli("delivery", "--json"))["rows"], {"feed": 6, "notifications": 4})
        self.run_cli("rows", "--feed", "0", "--notifications", "0")
        self.assertNotIn("rows", omabox.load_state())

    def test_rows_outside_the_range_are_refused_and_ignored_in_state(self):
        for bad in ("51", "-1", "x"):
            with self.subTest(bad), self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                self.run_cli("rows", "--feed", bad)
        state = omabox.load_state()
        state["rows"] = {"feed": 999, "notifications": "7"}
        self.assertEqual(omabox.panel_rows(state), {"feed": 0, "notifications": 0})


class LoopbackOpenerTest(unittest.TestCase):
    def test_rsshub_opener_refuses_redirects_and_https(self):
        elsewhere = socket.socket()
        self.addCleanup(elsewhere.close)
        elsewhere.bind(("127.0.0.1", 0))
        elsewhere.listen()
        elsewhere.settimeout(0.3)
        other = elsewhere.getsockname()[1]
        for target in (f"https://127.0.0.1:{other}/", f"http://127.0.0.1:{other}/"):
            port, asked = recording_server(self, status=302, headers={"Location": target})
            with self.assertRaises(ValueError):
                omabox.LOOPBACK_OPENER.open(f"http://127.0.0.1:{port}/twitter/user/rowanvale", timeout=5)
            self.assertEqual(asked, ["/twitter/user/rowanvale"])
        with self.assertRaises(urllib.error.URLError):
            omabox.LOOPBACK_OPENER.open(f"https://127.0.0.1:{other}/", timeout=5)
        with self.assertRaises(socket.timeout):
            elsewhere.accept()
        self.assertFalse(any(isinstance(h, urllib.request.HTTPSHandler) for h in omabox.LOOPBACK_OPENER.handlers))

    def test_rsshub_opener_still_reads_a_plain_answer(self):
        port, asked = recording_server(self, body=b'{"items": []}')
        with omabox.LOOPBACK_OPENER.open(f"http://127.0.0.1:{port}/twitter/user/rowanvale", timeout=5) as response:
            self.assertEqual(response.read(), b'{"items": []}')
        with mock.patch.dict(os.environ, {"http_proxy": "http://192.0.2.1:3128"}):
            with omabox.LOOPBACK_OPENER.open(f"http://127.0.0.1:{port}/", timeout=5):
                pass
        self.assertEqual(asked, ["/twitter/user/rowanvale", "/"])


class CopyScriptTest(unittest.TestCase):
    """The panel's wl-copy script, run against a stand-in wl-copy that records its argv and stdin."""

    def setUp(self):
        text = (BIN.parent.parent / "Panel.qml").read_text()
        self.command = json.loads(re.search(r"id: copyProc.*?command: (\[.*?\])\n", text, re.S).group(1))
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(subprocess.run, ["rm", "-rf", "--", str(self.dir)])

    def copy(self, text, mode="sensitive", supports_sensitive=True, fails=False):
        flag = "--sensitive" if supports_sensitive else "--nothing"
        (self.dir / "wl-copy").write_text(f"""#!/bin/sh
if [ "$1" = --help ]; then echo "  {flag}  hint"; exit 0; fi
for a in "$@"; do [ "$a" = --sensitive ] && [ {flag} != --sensitive ] && exit 1; done
{"exit 1" if fails else ""}
printf '%s\\n' "$@" > "{self.dir}/args"; cat > "{self.dir}/text"
""")
        (self.dir / "wl-copy").chmod(0o700)
        for name in ("args", "text"):
            (self.dir / name).unlink(missing_ok=True)
        env = {"PATH": f"{self.dir}:/usr/bin:/bin", "OMABOX_COPY": mode}
        code = subprocess.run(self.command, input=text.encode(), env=env, timeout=10).returncode
        args = (self.dir / "args").read_text().split("\n") if (self.dir / "args").exists() else None
        copied = (self.dir / "text").read_text() if (self.dir / "text").exists() else None
        return code, args, copied

    def test_notification_copy_is_sensitive_and_off_argv(self):
        code, args, copied = self.copy("Your sign-in code is 482913\n\n")
        self.assertEqual(code, 0)
        self.assertIn("--sensitive", args)
        self.assertEqual(copied, "Your sign-in code is 482913\n\n")
        self.assertFalse(any("482913" in a for a in args))

    def test_link_copy_stays_plain(self):
        code, args, copied = self.copy("https://example.com/p", mode="plain")
        self.assertEqual((code, copied), (0, "https://example.com/p"))
        self.assertNotIn("--sensitive", args)

    def test_old_wl_copy_without_the_flag_still_copies(self):
        code, args, copied = self.copy("code 482913", supports_sensitive=False)
        self.assertEqual((code, copied), (0, "code 482913"))
        self.assertNotIn("--sensitive", args)

    def test_a_failing_wl_copy_is_not_retried_unmarked(self):
        code, args, copied = self.copy("code 482913", fails=True)
        self.assertNotEqual(code, 0)
        self.assertIsNone(copied)


class YtdlHookTest(unittest.TestCase):
    """Real mpv with Omabox's flags, a recorder standing in for omabox-ytdl, and addresses on a closed port."""

    def mpv(self, files, extra=()):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(subprocess.run, ["rm", "-rf", "--", str(root)])
        (root / "recorder").write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" >> "{root}/seen"\nexit 1\n')
        (root / "recorder").chmod(0o700)
        with mock.patch.object(omabox, "YTDL_WRAPPER", root / "recorder"), \
                mock.patch.object(omabox.shutil, "which", lambda name: "/usr/bin/" + name):
            argv = omabox.direct_player_argv(files, 0)
        flags = argv[1:argv.index("--")]
        env = {"PATH": os.environ.get("PATH", "/usr/bin"), "HOME": str(root), "XDG_CONFIG_HOME": str(root / "c")}
        subprocess.run(["mpv", "--no-config", "--vo=null", "--ao=null", "--idle=no", *extra, *flags, "--", *files],
                       env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
        return (root / "seen").read_text().splitlines() if (root / "seen").exists() else []

    @unittest.skipUnless(omabox.shutil.which("mpv"), "needs mpv")
    def test_only_tokens_reach_the_wrapper(self):
        failing = "http://127.0.0.1:9/ab12cd/DASHPlaylist.mpd"
        self.assertEqual(self.mpv([failing]), [])
        self.assertEqual(self.mpv([failing], extra=["--script-opts-append=ytdl_hook-try_ytdl_first=yes"]), [])
        token = "ytdl://b-_a7ghi6-upq3_Cr-gRpg"
        seen = self.mpv([token, failing], extra=["--script-opts-append=ytdl_hook-try_ytdl_first=yes"])
        self.assertIn("b-_a7ghi6-upq3_Cr-gRpg", seen)
        self.assertFalse(any("127.0.0.1" in arg for arg in seen), seen)


class MediaHeadTest(unittest.TestCase):
    MPD = (b'<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" profiles="urn:mpeg:dash:profile:isoff-on-demand:2011" type="static">'
           b'<Period><AdaptationSet><Representation id="1" bandwidth="1"><BaseURL>http://192.0.2.10/admin</BaseURL>'
           b'</Representation></AdaptationSet></Period></MPD>')

    def test_manifests_dressed_as_boxes_are_refused(self):
        id3 = b"ID3\x03\x00\x00\x00\x00\x10\x7f"
        for head in (b"<!--free-->\n" + self.MPD, b"<?a moov ?>" + self.MPD, b"    free" + self.MPD,
                     b"<!--free" + b"-" * 700 + b"-->" + self.MPD, b"\x00\x00\x00\x10free" + b"<!-- x -->" + self.MPD,
                     id3 + b"#EXTM3U\nhttp://192.0.2.10/a.ts\n", id3 + b"[playlist]\nFile1=http://192.0.2.10/a\n",
                     b"\x00\x00\x00\x18ftypisom" + bytes(16) + b"<?xml version='1.0'?>" + self.MPD,
                     b"OggS" + bytes(30) + b"<smil><body/></smil>", b"\x00\x00\x00\x08wide" + b"<?a mdat?>" + self.MPD,
                     b"\x00\x00\x00\x14ftyp\x00\x01\x02\x03" + bytes(600), b"\x00\x00\x00\x00moov" + bytes(600)):
            self.assertFalse(omabox.media_head(head[:omabox.MEDIA_HEAD_BYTES]), head[:24])
        # no marker in reach: the text box header alone gives them away
        for head in (b"<?a moov ?>", b"    free", b"\x00\x00\x00\x08wide<?a mdat?>", b"\x00\x00\x00\x08free\n\n\n\nmoov",
                     b"\x00\x01\x00\x00free", b"\x00\x00\x00\x01free\x00\x00\x00\x00\x00\x01\x00\x00",
                     b"\x00\x01\x00\x00moov", b"\x00\x01\x00\x00mdat", b"\x00\x00\x00\x01mdat\x00\x00\x00\x01\x00\x00\x00\x00"):
            self.assertFalse(omabox.media_head(head + b"x" * 600), head)
        self.assertTrue(omabox.media_head(b"\x00\x01\x00\x00moov\x00\x00\x00\x6cmvhd" + bytes(600)))
        self.assertTrue(omabox.media_head(b"\x00\x00\x00\x08wide\x00\x01\x00\x00mdat" + bytes(range(256)) * 2))

    @unittest.skipUnless(omabox.shutil.which("ffmpeg"), "needs ffmpeg")
    def test_real_media_heads_pass(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(subprocess.run, ["rm", "-rf", "--", str(root)])
        video = ["-f", "lavfi", "-i", "testsrc=duration=1:size=64x48:rate=5", "-pix_fmt", "yuv420p"]
        audio = ["-f", "lavfi", "-i", "sine=duration=1"]
        cases = {"a.mp4": video, "b.mp4": video + ["-movflags", "+faststart"], "c.mov": video, "d.webm": video,
                 "e.mkv": video, "f.ts": video, "g.mp4": video + ["-movflags", "+frag_keyframe+empty_moov"],
                 "h.mp3": audio + ["-metadata", "title=Some <title>"], "i.aac": audio, "j.ogg": audio, "k.opus": audio,
                 "l.flac": audio, "m.wav": audio, "n.m4a": audio, "o.avi": video, "p.flv": video}
        for name, inputs in cases.items():
            subprocess.run(["ffmpeg", "-loglevel", "error", *inputs, str(root / name)], check=True, timeout=60)
            head = (root / name).read_bytes()[:omabox.MEDIA_HEAD_BYTES]
            self.assertTrue(omabox.media_head(head), (name, head[:16]))


class SanitizeDepthTest(unittest.TestCase):
    def test_nesting_is_capped_and_the_output_balanced(self):
        body, text = omabox.sanitize("<b>" * 500 + "deep" + "</i>" * 500 + '<a href="https://example.com/">l</a>')
        self.assertEqual(body.count("<b>"), omabox.MAX_OPEN_TAGS)
        self.assertEqual(body.count("<b>"), body.count("</b>"))
        self.assertEqual(text, "deepl")
        self.assertEqual(omabox.sanitize("<p><b>x</b> <i>y</i></p>")[0], "<p><b>x</b> <i>y</i></p>")

    def test_unclosed_tags_cost_linear_time(self):
        def cost(n):
            started = time.perf_counter()
            omabox.sanitize("<b>" * n + "</i>" * n)
            return time.perf_counter() - started
        cost(1000)
        small, big = min(cost(5000) for _ in range(3)), cost(40000)
        self.assertLess(big / small, 20, (small, big))


class ArticleDepthTest(unittest.TestCase):
    def test_text_sizes_match_text_size_on_every_node(self):
        pick = random.Random(7)
        bits = ["<p>", "</p>", "<div>", "</div>", "<a href='/x'>", "</a>", " ", "  word ", "text", "\n", "<br>",
                "<blockquote>", "</blockquote>", "\u00a0", "<span>", "</span>", "ipsum dolor sit "]
        for _ in range(200):
            tree = omabox.PageTree()
            tree.feed("".join(pick.choice(bits) for _ in range(pick.randint(1, 300))))
            tree.close()
            sizes, links = omabox.text_sizes(tree.root)
            for node in [tree.root, *omabox.walk(tree.root)]:
                self.assertEqual(sizes[id(node)], omabox.text_size(node))
                self.assertEqual(links[id(node)], sum(omabox.text_size(a) for a in omabox.walk(node) if a.tag == "a"))

    def test_deep_nesting_costs_linear_time(self):
        def cost(depth):
            page = "<html><body>" + "<blockquote>x " * depth + "<a>y " * depth + "word " * 40000 + "</body></html>"
            started = time.perf_counter()
            omabox.extract_article(page, "https://example.com/")
            return time.perf_counter() - started
        cost(30)
        small, big = min(cost(30) for _ in range(3)), cost(240)
        self.assertLess(big / small, 8, (small, big))


if __name__ == "__main__":
    unittest.main()
