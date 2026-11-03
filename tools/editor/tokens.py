"""The design tokens: the `--name: value;` lines of the :root block in docs/styles.css.

Reading returns each token with a kind the editor uses to pick a control. Writing changes only the value on
a token's own line; indentation, order, comments and every other line of the stylesheet stay as they are.
"""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

LINE = re.compile(r"^(?P<indent>\s*)(?P<name>--[A-Za-z0-9_-]+)\s*:\s*(?P<value>.*?)\s*;(?P<rest>.*)$")
NUM = r"-?\d+(?:\.\d+)?"
CLAMP = re.compile(r"clamp\(\s*(%s)px\s*,\s*(%s)vw\s*,\s*(%s)px\s*\)$" % (NUM, NUM, NUM))


class TokenError(Exception):
    pass


def _root_lines(css: str) -> Tuple[List[str], int, int]:
    lines = css.split("\n")
    start = next((i for i, l in enumerate(lines) if l.strip() == ":root{"), -1)
    if start < 0:
        raise TokenError("no ':root{' block in the stylesheet")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].strip() == "}"), -1)
    if end < 0:
        raise TokenError("the :root block never closes")
    return lines, start, end


def kind_of(value: str) -> str:
    v = value.strip()
    if re.fullmatch(r"#[0-9a-fA-F]{3,8}", v):
        return "color"
    if re.fullmatch(NUM + r"px", v):
        return "px"
    if CLAMP.fullmatch(v):
        return "clamp"
    if re.fullmatch(NUM, v):
        return "number"
    if re.fullmatch(r"\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}", v):
        return "rgb"                                  # an r,g,b triple for rgba(var(--x), alpha)
    if '"' in v or "," in v:
        return "font"
    return "text"


def uses(css: str, name: str) -> int:
    return len(re.findall(r"var\(\s*" + re.escape(name) + r"\s*[,)]", css))


def read_tokens(css: str) -> List[Dict[str, object]]:
    lines, start, end = _root_lines(css)
    out = []
    for i in range(start + 1, end):
        m = LINE.match(lines[i])
        if not m:
            continue
        name, value = m.group("name"), m.group("value")
        out.append({"name": name, "value": value, "kind": kind_of(value), "uses": uses(css, name)})
    return out


def _check_value(name: str, value: str) -> str:
    v = value.strip()
    if not v:
        raise TokenError("%s: a value is required" % name)
    if len(v) > 200 or re.search(r"[;{}<>\n]|/\*|\*/", v):
        raise TokenError("%s: that value would break the stylesheet" % name)
    return v


def set_tokens(css: str, values: Dict[str, str]) -> str:
    lines, start, end = _root_lines(css)
    todo = {k: _check_value(k, v) for k, v in values.items()}
    for i in range(start + 1, end):
        m = LINE.match(lines[i])
        if m and m.group("name") in todo:
            lines[i] = "%s%s:%s;%s" % (m.group("indent"), m.group("name"), todo.pop(m.group("name")), m.group("rest"))
    if todo:
        raise TokenError("not a token in :root: %s" % ", ".join(sorted(todo)))
    return "\n".join(lines)
