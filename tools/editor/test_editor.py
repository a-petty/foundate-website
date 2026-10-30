"""Tests for the local editor. Run from the website checkout:

    uv run --with pytest python -m pytest tools/editor -q
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pages as pg      # noqa: E402
import serve            # noqa: E402
import tokens as tk     # noqa: E402

REPO = HERE.parent.parent
DOCS = REPO / "docs"

SMALL = """<!doctype html>
<html><head><title>T</title><script>var x = "<p>not a p</p>";</script></head>
<body>
  <header class="site-header"><a class="wordmark" href="/">Foundate</a>
    <nav><ul>
      <li><a href="/work/">Work</a></li>
    </ul></nav></header>
  <main id="main">
    <section id="one" aria-labelledby="t1">
      <h1 id="t1">First &amp; foremost</h1>
      <p class="lede">
        Two lines
        of text
      </p>
      <img src="x.png" alt="">
      <br/>
    </section>
    <!-- a comment with <p>tags</p> -->
    <section class="two">
      <div><h2>Second</h2><p>Body with <a href="/x">a link</a>.</p></div>
    </section>
    <section class="three" hidden>
      <h2>Third</h2>
    </section>
  </main>
  <footer><p class="copyright">© 2026 Foundate LLC</p></footer>
</body></html>
"""


# --- parsing ---------------------------------------------------------------------------------------

def test_spans_are_exact():
    d = pg.Doc(SMALL)
    h1 = d.by_id("t1")
    assert d.inner(h1) == "First &amp; foremost"
    assert d.outer(h1) == '<h1 id="t1">First &amp; foremost</h1>'
    assert d.text_of(h1) == "First & foremost"
    img = d.find(lambda n: n.tag == "img")
    assert img.start_end == img.end == img.end_end and d.outer(img) == '<img src="x.png" alt="">'
    br = d.find(lambda n: n.tag == "br")
    assert d.outer(br) == "<br/>"


def test_editables_are_outermost_text_blocks_only():
    d = pg.Doc(SMALL)
    got = [(n.tag, d.text_of(n)) for n in d.editables]
    assert got == [("a", "Foundate"), ("li", "Work"), ("h1", "First & foremost"), ("p", "Two lines of text"),
                   ("h2", "Second"), ("p", "Body with a link."), ("h2", "Third"), ("p", "© 2026 Foundate LLC")]
    assert "T" not in [t for _, t in got]                     # <title> is in <head>


def test_sections_and_labels():
    d = pg.Doc(SMALL)
    infos = d.summary()["sections"]
    assert [i["label"] for i in infos] == ["Header", "First & foremost", "Second", "Third", "Footer"]
    assert [i["hidden"] for i in infos] == [False, False, False, True, False]
    assert [i["movable"] for i in infos] == [False, True, True, True, False]
    assert infos[0]["shared"] and infos[-1]["shared"]
    assert d.is_shared(d.editables[0]) and not d.is_shared(d.editables[2])


def test_annotation_round_trips():
    d = pg.Doc(SMALL)
    a = d.annotated()
    assert 'data-ed="0"' in a and 'data-ed-sec="4"' in a
    assert re.sub(r' data-ed(?:-sec)?="\d+"', "", a) == SMALL


# --- edits -----------------------------------------------------------------------------------------

def test_set_text_keeps_indentation_and_touches_nothing_else():
    d = pg.Doc(SMALL)
    i = next(k for k, n in enumerate(d.editables) if n.attr("class") == "lede")
    new = pg.set_text(SMALL, i, "Two lines of text", "One line")
    assert '<p class="lede">\n        One line\n      </p>' in new
    assert re.sub(r'<p class="lede">.*?</p>', "", new, flags=re.S) == re.sub(r'<p class="lede">.*?</p>', "", SMALL, flags=re.S)


def test_set_text_refuses_stale_block_or_empty():
    d = pg.Doc(SMALL)
    i = next(k for k, n in enumerate(d.editables) if n.attr("id") == "t1")
    with pytest.raises(pg.EditError):
        pg.set_text(SMALL, i, "not what is there", "x")
    with pytest.raises(pg.EditError):
        pg.set_text(SMALL, i, "First & foremost", "<div>block</div>")
    with pytest.raises(pg.EditError):
        pg.set_text(SMALL, i, "First & foremost", "   ")
    with pytest.raises(pg.EditError):
        pg.set_text(SMALL, i, "First & foremost", '<a href="javascript:alert(1)">x</a>')
    with pytest.raises(pg.EditError):
        pg.set_text(SMALL, 99, "x", "y")


def test_set_text_accepts_entities_and_inline_markup():
    d = pg.Doc(SMALL)
    i = next(k for k, n in enumerate(d.editables) if d.text_of(n) == "Body with a link.")
    new = pg.set_text(SMALL, i, 'Body with <a href="/x">a link</a>.', 'Body with <a href="/y">another</a>, <em>now</em>.')
    assert '<p>Body with <a href="/y">another</a>, <em>now</em>.</p>' in new


def test_hidden_toggles_are_minimal_and_idempotent():
    new = pg.set_hidden(SMALL, 1, True)
    assert '<section id="one" aria-labelledby="t1" hidden>' in new
    assert pg.set_hidden(new, 1, True) == new
    back = pg.set_hidden(new, 1, False)
    assert back == SMALL
    assert pg.set_hidden(SMALL, 3, False).count("hidden") == SMALL.count("hidden") - 1


def test_move_swaps_whole_sections_only():
    new = pg.move_section(SMALL, 1, +1)
    assert new.index('<section class="two">') < new.index('<section id="one"')
    assert pg.move_section(new, 2, -1) == SMALL                # back where it was
    with pytest.raises(pg.EditError):
        pg.move_section(SMALL, 1, -1)                          # already at the top
    with pytest.raises(pg.EditError):
        pg.move_section(SMALL, 0, +1)                          # the header stays put


def test_same_text_finds_identical_elements():
    assert pg.same_text(SMALL, "li", "<a href=\"/work/\">Work</a>") == [1]
    assert pg.same_text(SMALL, "p", "nothing like this") == []


def test_locator_resolves_the_same_place_on_another_page():
    d = pg.Doc(SMALL)
    li = d.editables[1]
    loc = d.locator(li)
    assert loc == ("header", (("nav", 1), ("ul", 0), ("li", 0)))          # the wordmark is the header's first child
    other = SMALL.replace('<li><a href="/work/">Work</a></li>', '<li><a href="/work/" aria-current="page">Work</a></li>')
    d2 = pg.Doc(other)
    m = d2.resolve(loc)
    assert m is not None and d2.text_of(m) == "Work" and d2.editable_index(m) == 1
    h1 = d.by_id("t1")
    assert d.locator(h1) == ("#one", (("h1", 0),))
    assert d2.resolve(("#nowhere", (("h1", 0),))) is None


def test_retarget_keeps_the_other_pages_own_attributes():
    before, after = '<a href="/work/">Work</a>', '<a href="/work/">Our work</a>'
    other = '<a href="/work/" aria-current="page">Work</a>'
    assert pg.retarget(before, after, other) == '<a href="/work/" aria-current="page">Our work</a>'
    assert pg.retarget("Plain", "Changed", "Plain") == "Changed"
    assert pg.retarget("Plain", "Changed", "Different") is None            # not the same text there
    assert pg.retarget("Plain", "Now <em>bold</em>", "Plain") is None        # markup no longer lines up


# --- tokens ----------------------------------------------------------------------------------------

CSS = """/* head */
:root{
  --paper:#f5f2eb;
  --radius:4px;   /* corners */
  --gutter:clamp(20px,5vw,64px);
  --leading:1.6;
  --sans:"IBM Plex Sans",Arial,sans-serif;
}
body{background:var(--paper);border-radius:var(--radius);padding:var(--gutter);font:var(--sans)}
.x{color:var(--paper)}
"""


def test_tokens_read_kinds_and_uses():
    t = {x["name"]: x for x in tk.read_tokens(CSS)}
    assert t["--paper"]["kind"] == "color" and t["--paper"]["uses"] == 2
    assert t["--radius"]["kind"] == "px" and t["--radius"]["value"] == "4px"
    assert t["--gutter"]["kind"] == "clamp"
    assert t["--leading"]["kind"] == "number"
    assert t["--sans"]["kind"] == "font"


def test_tokens_write_only_the_value():
    new = tk.set_tokens(CSS, {"--radius": "8px", "--paper": "#ffffff"})
    assert "  --radius:8px;   /* corners */" in new
    assert "  --paper:#ffffff;" in new
    assert new.splitlines()[0] == "/* head */" and new.endswith(".x{color:var(--paper)}\n")
    with pytest.raises(tk.TokenError):
        tk.set_tokens(CSS, {"--nope": "1px"})
    with pytest.raises(tk.TokenError):
        tk.set_tokens(CSS, {"--radius": "4px; } body{display:none"})


# --- the real pages --------------------------------------------------------------------------------

def test_real_pages_parse_and_round_trip():
    for f in sorted(DOCS.glob("**/index.html")):
        text = f.read_text(encoding="utf-8")
        d = pg.Doc(text)
        labels = [s["label"] for s in d.summary()["sections"]]
        assert labels[0] == "Header" and labels[-1] == "Footer", f
        assert len(labels) >= 4 and len(d.editables) >= 10, f
        assert re.sub(r' data-ed(?:-sec)?="\d+"', "", d.annotated()) == text, f


def test_real_stylesheet_tokens():
    t = {x["name"]: x for x in tk.read_tokens((DOCS / "styles.css").read_text(encoding="utf-8"))}
    assert t["--green"]["value"] == "#1e4d3b" and t["--green"]["uses"] > 5
    assert t["--size-h2"]["kind"] == "clamp" and t["--size-h2"]["uses"] >= 1
    assert t["--text"]["kind"] == "px" and t["--section-pad"]["uses"] >= 2
    assert t["--hero-tint"]["kind"] == "rgb" and t["--hero-tint"]["uses"] == 6
    assert tk.kind_of("30, 77, 59") == "rgb" and tk.kind_of('"Zilla Slab",serif') == "font"


# --- the server, against a scratch copy of the site ------------------------------------------------

@pytest.fixture
def served(tmp_path):
    root = tmp_path / "site"
    root.mkdir()
    shutil.copytree(DOCS, root / "docs")
    for cmd in (["git", "init", "-q", "-b", "main"], ["git", "config", "user.email", "t@example.com"],
                ["git", "config", "user.name", "t"], ["git", "add", "-A"], ["git", "commit", "-qm", "site"]):
        subprocess.run(cmd, cwd=str(root), check=True, capture_output=True)
    srv = serve.make_server(root, 0)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    base = "http://127.0.0.1:%d" % srv.server_port

    def call(path, body=None, origin=True):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(base + path, data=data, method="POST" if data else "GET")
        if data:
            req.add_header("Content-Type", "application/json")
            if origin:
                req.add_header("Origin", base)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read() or b"{}") if "json" in r.headers.get("Content-Type", "") else r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    yield root, call
    srv.shutdown()


def test_server_state_pages_and_preview(served):
    root, call = served
    code, st = call("/__api/state")
    assert code == 200 and st["branch"] == "main" and st["changed"] == []
    assert [p["path"] for p in st["pages"]][:4] == ["/", "/work/", "/how-we-work/", "/about/"]
    assert st["pages"][1]["label"] == "Work"
    code, page = call("/__api/page?path=/")
    assert code == 200 and page["sections"][1]["label"].startswith("AI transformation")
    code, html = call("/?__edit=1")
    assert code == 200 and 'data-ed="0"' in html and "/__editor/overlay.js" in html
    code, plain = call("/")
    assert "data-ed" not in plain and "overlay.js" not in plain          # the site itself is untouched
    code, _ = call("/../tools/editor/serve.py")
    assert code == 404


def test_server_text_edit_everywhere_and_diff(served):
    root, call = served
    home = pg.Doc((root / "docs/index.html").read_text())
    hdr_idx = next(i for i, n in enumerate(home.editables) if n.tag == "li" and home.text_of(n) == "Work")
    code, same = call("/__api/same?path=/&index=%d" % hdr_idx)
    assert code == 200 and sorted(p["path"] for p in same["pages"]) == ["/about/", "/how-we-work/", "/work/"]
    current_before = (root / "docs/work/index.html").read_text().count("aria-current")
    code, r = call("/__api/text", {"path": "/", "index": hdr_idx, "before": '<a href="/work/">Work</a>',
                                   "after": '<a href="/work/">Our work</a>', "everywhere": True})
    assert code == 200 and len(r["changed"]) == 4 and r["skipped"] == [], r
    for f in root.glob("docs/**/index.html"):
        t = f.read_text()
        assert t.count(">Our work</a></li>") == 1 and ">Work</a></li>" in t, f    # the header changed, the footer did not
    assert (root / "docs/work/index.html").read_text().count("aria-current") == current_before
    code, d = call("/__api/diff")
    assert code == 200 and len(d["changed"]) == 4 and "+        <li><a href=\"/work/\">Our work</a></li>" in d["diff"]
    code, r = call("/__api/text", {"path": "/", "index": hdr_idx, "before": "stale", "after": "x"})
    assert code == 400 and "reload" in r["error"]


def test_server_sections_tokens_discard_commit(served):
    root, call = served
    code, page = call("/__api/section", {"path": "/about/", "index": 2, "action": "hide"})
    assert code == 200 and page["sections"][2]["hidden"] is True
    assert ' hidden>' in (root / "docs/about/index.html").read_text()
    code, page = call("/__api/section", {"path": "/about/", "index": 2, "action": "down"})
    assert code == 200 and page["sections"][3]["hidden"] is True       # it moved, hidden and all
    code, r = call("/__api/tokens", {"values": {"--green": "#123456"}})
    assert code == 200 and next(t for t in r["tokens"] if t["name"] == "--green")["value"] == "#123456"
    code, r = call("/__api/tokens", {"values": {"--green": "red; }"}})
    assert code == 400
    code, r = call("/__api/commit", {"message": ""})
    assert code == 400
    code, r = call("/__api/commit", {"message": "Hide the statement; darker green"})
    assert code == 200 and r["branch"].startswith("edit/") and len(r["sha"]) >= 7
    code, st = call("/__api/state")
    assert st["branch"] == r["branch"] and st["changed"] == []
    code, r = call("/__api/section", {"path": "/", "index": 1, "action": "hide"})
    assert code == 200 and " hidden>" in (root / "docs/index.html").read_text()
    code, st = call("/__api/discard", {})
    assert code == 200 and st["changed"] == []
    assert " hidden>" not in (root / "docs/index.html").read_text()


def test_server_refuses_cross_origin_writes(served):
    root, call = served
    code, r = call("/__api/tokens", {"values": {"--green": "#000000"}}, origin=False)
    assert code == 403
