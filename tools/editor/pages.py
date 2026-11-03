"""HTML with source positions, for exact edits that keep a page's formatting.

The site's pages are hand-written HTML. Rewriting them through a DOM would reflow every line, so the
editor never does that. It parses a page into a tree that remembers where each element starts and ends
in the source, and every change is a splice of one of those spans. Nothing outside the span changes.

Works on the system Python (3.9): standard library only.
"""
from __future__ import annotations

import html as htmlmod
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Callable, Iterator, List, Optional, Tuple

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
# Elements whose inner HTML is offered for editing when they hold only text and inline markup.
TEXT_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "dt", "dd", "figcaption", "blockquote", "summary",
             "td", "th", "a", "span", "small", "strong", "em", "cite", "label", "button", "time"}
# Markup allowed inside an editable element, and in the text that replaces it.
INLINE = {"a", "span", "em", "strong", "b", "i", "small", "abbr", "time", "code", "sup", "sub", "br", "wbr",
          "cite", "mark", "kbd"}
SKIP = {"head", "script", "style", "svg", "template", "noscript"}
SHARED = ("header", "footer")       # body-level elements repeated on every page


class EditError(Exception):
    """A change the editor refuses. The message is shown to the person as it is."""


@dataclass
class Node:
    tag: str
    attrs: List[Tuple[str, Optional[str]]]
    start: int                      # offset of "<"
    start_end: int                  # offset just past ">" of the start tag
    end: int = -1                   # offset of "</" (a void element: same as start_end)
    end_end: int = -1               # offset just past ">" of the end tag
    parent: Optional["Node"] = None
    children: List["Node"] = field(default_factory=list)

    def attr(self, name: str) -> Optional[str]:
        for k, v in self.attrs:
            if k == name:
                return v if v is not None else ""
        return None

    def has_attr(self, name: str) -> bool:
        return any(k == name for k, _ in self.attrs)

    def descendants(self) -> Iterator["Node"]:
        for c in self.children:
            yield c
            yield from c.descendants()

    def ancestors(self) -> Iterator["Node"]:
        n = self.parent
        while n is not None:
            yield n
            n = n.parent


class _Parser(HTMLParser):
    """Builds the tree. Handlers run before the parser advances, so getpos() is the construct's start."""

    def __init__(self, text: str):
        super().__init__(convert_charrefs=False)
        self.text = text
        self.line_starts = [0] + [m.end() for m in re.finditer("\n", text)]
        self.root = Node("#root", [], 0, 0, len(text), len(text))
        self.stack = [self.root]

    def _abs(self) -> int:
        line, col = self.getpos()
        return self.line_starts[line - 1] + col

    def _open(self, tag: str, attrs) -> Tuple[Node, str]:
        start = self._abs()
        raw = self.get_starttag_text() or ""
        node = Node(tag, list(attrs), start, start + len(raw), parent=self.stack[-1])
        self.stack[-1].children.append(node)
        return node, raw

    def handle_starttag(self, tag, attrs):
        node, raw = self._open(tag, attrs)
        if tag in VOID or raw.endswith("/>"):
            node.end = node.end_end = node.start_end
        else:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        node, _ = self._open(tag, attrs)
        node.end = node.end_end = node.start_end

    def handle_endtag(self, tag):
        pos = self._abs()
        close = self.text.find(">", pos)
        close = len(self.text) if close < 0 else close + 1
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                for n in self.stack[i + 1:]:          # left open by the author; closed here
                    n.end = n.end_end = pos
                self.stack[i].end, self.stack[i].end_end = pos, close
                del self.stack[i:]
                return
        # a stray end tag closes nothing


def normalize(s: str) -> str:
    """Text as a person would compare it: entities decoded, whitespace collapsed."""
    return re.sub(r"\s+", " ", htmlmod.unescape(s)).strip()


def strip_tags(s: str) -> str:
    return re.sub(r"<[^>]*>", "", s)


class Doc:
    def __init__(self, text: str):
        self.text = text
        p = _Parser(text)
        p.feed(text)
        p.close()
        for n in p.stack[1:]:                         # never closed: runs to the end of the file
            n.end = n.end_end = len(text)
        self.root = p.root
        self.editables: List[Node] = self._collect_editables()
        self.sections: List[Node] = self._collect_sections()

    # --- reading -------------------------------------------------------------------------------

    def inner(self, n: Node) -> str:
        return self.text[n.start_end:n.end]

    def outer(self, n: Node) -> str:
        return self.text[n.start:n.end_end]

    def text_of(self, n: Node) -> str:
        return normalize(strip_tags(self.inner(n)))

    def find(self, pred: Callable[[Node], bool]) -> Optional[Node]:
        for n in self.root.descendants():
            if pred(n):
                return n
        return None

    def by_id(self, id_: str) -> Optional[Node]:
        return self.find(lambda n: n.attr("id") == id_)

    def is_shared(self, n: Node) -> bool:
        """Inside the header or footer, which every page repeats."""
        for a in [n] + list(n.ancestors()):
            if a.tag in SHARED and a.parent is not None and a.parent.tag == "body":
                return True
        return False

    def _is_text_block(self, n: Node) -> bool:
        if n.tag in VOID or n.end < n.start_end:
            return False
        for d in n.descendants():
            if d.tag not in INLINE:
                return False
        return bool(strip_tags(self.inner(n)).strip())

    def _collect_editables(self) -> List[Node]:
        out: List[Node] = []

        def visit(n: Node) -> None:
            if n.tag in SKIP:
                return
            if n.tag in TEXT_TAGS and self._is_text_block(n):
                out.append(n)                         # the outermost text block wins
                return
            for c in n.children:
                visit(c)

        for c in self.root.children:
            visit(c)
        return out

    def _collect_sections(self) -> List[Node]:
        body = self.find(lambda n: n.tag == "body")
        if body is None:
            return []
        main = self.find(lambda n: n.tag == "main")
        out = [c for c in body.children if c.tag == "header"]
        if main is not None:
            out.extend(c for c in main.children if c.tag not in VOID and c.tag not in SKIP)
        out.extend(c for c in body.children if c.tag == "footer")
        return out

    # --- the same element on another page ------------------------------------------------------

    def locator(self, n: Node) -> Tuple[str, Tuple[Tuple[str, int], ...]]:
        """Where an element sits: a region (the header, the footer, or the nearest ancestor with an id,
        else the body) and the tag/position chain below it. Pages built from the same template share these."""
        chain: List[Tuple[str, int]] = []
        cur = n
        while True:
            p = cur.parent
            if p is None or p.tag == "#root":
                return ("body", tuple(reversed(chain)))
            if cur.tag in SHARED and p.tag == "body":
                return (cur.tag, tuple(reversed(chain)))
            chain.append((cur.tag, p.children.index(cur)))
            if p.attr("id") is not None and p.tag != "body":
                return ("#" + (p.attr("id") or ""), tuple(reversed(chain)))
            if p.tag == "body":
                return ("body", tuple(reversed(chain)))
            cur = p

    def resolve(self, loc: Tuple[str, Tuple[Tuple[str, int], ...]]) -> Optional[Node]:
        region, chain = loc
        if region in SHARED:
            body = self.find(lambda x: x.tag == "body")
            node = next((c for c in body.children if c.tag == region), None) if body else None
        elif region.startswith("#"):
            node = self.by_id(region[1:])
        else:
            node = self.find(lambda x: x.tag == "body")
        for tag, idx in chain:
            if node is None or idx >= len(node.children) or node.children[idx].tag != tag:
                return None
            node = node.children[idx]
        return node

    def editable_index(self, n: Node) -> Optional[int]:
        for i, e in enumerate(self.editables):
            if e is n:
                return i
        return None

    def section_label(self, n: Node) -> str:
        if n.tag in SHARED and n.parent is not None and n.parent.tag == "body":
            return n.tag.capitalize()
        ref = n.attr("aria-labelledby")
        if ref:
            t = self.by_id(ref)
            if t is not None and self.text_of(t):
                return self.text_of(t)[:90]
        for d in n.descendants():
            if d.tag in ("h1", "h2", "h3") and self.text_of(d):
                return self.text_of(d)[:90]
        return n.attr("id") or n.attr("class") or n.tag

    def section_info(self, i: int, n: Node) -> dict:
        shared = n.tag in SHARED and n.parent is not None and n.parent.tag == "body"
        return {
            "id": i,
            "tag": n.tag,
            "label": self.section_label(n),
            "anchor": n.attr("id"),
            "hidden": n.has_attr("hidden"),
            "shared": shared,
            "movable": (not shared) and n.parent is not None and n.parent.tag == "main",
        }

    def summary(self) -> dict:
        return {"sections": [self.section_info(i, n) for i, n in enumerate(self.sections)],
                "editable": len(self.editables)}

    # --- annotation for the preview ------------------------------------------------------------

    @staticmethod
    def _attr_insert_pos(text: str, n: Node) -> int:
        raw = text[n.start:n.start_end]
        return n.start_end - (2 if raw.endswith("/>") else 1)

    def annotated(self) -> str:
        """The page with data-ed="N" on every editable element and data-ed-sec="N" on every section."""
        inserts = [(self._attr_insert_pos(self.text, n), ' data-ed="%d"' % i) for i, n in enumerate(self.editables)]
        inserts += [(self._attr_insert_pos(self.text, n), ' data-ed-sec="%d"' % i) for i, n in enumerate(self.sections)]
        inserts.sort(key=lambda x: x[0])
        out, last = [], 0
        for pos, s in inserts:
            out.append(self.text[last:pos])
            out.append(s)
            last = pos
        out.append(self.text[last:])
        return "".join(out)


# --- edits: each takes the file's text and returns the new text, or raises EditError ------------------

def _check_fragment(after: str) -> None:
    tags = re.findall(r"<\s*/?\s*([A-Za-z][A-Za-z0-9]*)", after)
    bad = sorted({t.lower() for t in tags if t.lower() not in INLINE})
    if bad:
        raise EditError("only inline markup can be edited here, not <%s>" % bad[0])
    if re.search(r"\son[a-z]+\s*=|javascript:", after, re.I):
        raise EditError("the site carries no scripts; that text was refused")


def set_text(text: str, index: int, before: str, after: str) -> str:
    """Replace the inner HTML of editable element `index`.

    `before` is what the editor showed, compared loosely (entities, whitespace). `after` is the new inner
    HTML; the element's own leading and trailing whitespace is kept so the file's indentation survives.
    """
    doc = Doc(text)
    if not 0 <= index < len(doc.editables):
        raise EditError("that element is not on the page any more; reload the preview")
    n = doc.editables[index]
    cur = doc.inner(n)
    if normalize(cur) != normalize(before):
        raise EditError("the text on disk is not what the editor showed; reload the preview and try again")
    new = after.strip()
    if not strip_tags(new).strip():
        raise EditError("empty text; hide the section instead of blanking it")
    _check_fragment(new)
    lead = cur[:len(cur) - len(cur.lstrip())]
    trail = cur[len(cur.rstrip()):]
    return text[:n.start_end] + lead + new + trail + text[n.end:]


TAG_SPLIT = re.compile(r"(<[^>]+>)")


def _tag_names(parts: List[str]) -> List[Optional[str]]:
    out: List[Optional[str]] = []
    for p in parts:
        if p.startswith("<"):
            m = re.match(r"</?\s*([A-Za-z0-9]+)", p)
            out.append(m.group(1).lower() if m else p)
        else:
            out.append(None)
    return out


def retarget(before: str, after: str, other: str) -> Optional[str]:
    """`after` adapted to another page's copy of the same element.

    The copy keeps its own tags (a nav item carries aria-current on its own page) and takes the new text
    between them. None when the markup does not line up, or the copy's text was not the same to begin with.
    """
    b, a, o = TAG_SPLIT.split(before), TAG_SPLIT.split(after), TAG_SPLIT.split(other)
    if not (len(b) == len(a) == len(o)):
        return None
    tb, ta, to = _tag_names(b), _tag_names(a), _tag_names(o)
    if not (tb == ta == to):
        return None
    for i, t in enumerate(tb):
        if t is None and normalize(b[i]) != normalize(o[i]):
            return None
    return "".join(o[i] if tb[i] is not None else a[i] for i in range(len(b)))


def same_text(text: str, tag: str, wanted: str) -> List[int]:
    """Indices of editable elements with this tag whose inner HTML normalizes to `wanted`."""
    doc = Doc(text)
    return [i for i, e in enumerate(doc.editables) if e.tag == tag and normalize(doc.inner(e)) == wanted]


def set_hidden(text: str, index: int, hidden: bool) -> str:
    doc = Doc(text)
    if not 0 <= index < len(doc.sections):
        raise EditError("that section is not on the page any more; reload the preview")
    n = doc.sections[index]
    raw = text[n.start:n.start_end]
    if hidden and not n.has_attr("hidden"):
        pos = Doc._attr_insert_pos(text, n)
        return text[:pos] + " hidden" + text[pos:]
    if not hidden and n.has_attr("hidden"):
        new_raw = re.sub(r"\s+hidden(?=[\s/>])", "", raw, count=1)
        return text[:n.start] + new_raw + text[n.start_end:]
    return text


def move_section(text: str, index: int, delta: int) -> str:
    """Swap section `index` with its neighbour (delta -1 up, +1 down) inside <main>."""
    doc = Doc(text)
    if not 0 <= index < len(doc.sections):
        raise EditError("that section is not on the page any more; reload the preview")
    n = doc.sections[index]
    if n.parent is None or n.parent.tag != "main":
        raise EditError("the header and footer stay where they are")
    sibs = [s for s in doc.sections if s.parent is n.parent]
    i = sibs.index(n)
    j = i + delta
    if not 0 <= j < len(sibs):
        raise EditError("already at the %s" % ("top" if delta < 0 else "bottom"))
    a, b = sorted((n, sibs[j]), key=lambda s: s.start)
    return (text[:a.start] + text[b.start:b.end_end] + text[a.end_end:b.start]
            + text[a.start:a.end_end] + text[b.end_end:])
