"""The local editor for foundate.ai.

Serves docs/ exactly as GitHub Pages does (same paths, same fonts) and, at /__editor/, a panel that edits
the site: design tokens, the text of any element, and which sections show and in what order. Every change is
written straight into docs/ as a minimal edit, so `git diff` shows exactly what was done and the usual
branch, pull request and merge flow publishes it.

Local only: binds 127.0.0.1, refuses cross-origin writes, and is never part of the published site
(GitHub Pages serves docs/ alone). Runs on the system Python (3.9), standard library only.

    python3 tools/editor/serve.py            # http://127.0.0.1:8766/__editor/
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import mimetypes
import re
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlsplit

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pages as pg      # noqa: E402
import tokens as tk     # noqa: E402

UI = HERE / "ui"
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("image/svg+xml", ".svg")


class ApiError(Exception):
    pass


class Site:
    """Everything the API does to the checkout. `root` is the website repo."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.docs = self.root / "docs"
        self.css = self.docs / "styles.css"
        if not self.css.exists():
            raise SystemExit("not the website checkout: %s has no docs/styles.css" % self.root)

    # --- pages ---------------------------------------------------------------------------------

    def pages(self) -> List[Dict[str, str]]:
        """Site pages in the order of the home page's navigation; anything else discovered after."""
        found = {"/": "Home"}
        for f in sorted(self.docs.glob("*/index.html")):
            found["/%s/" % f.parent.name] = f.parent.name.replace("-", " ").capitalize()
        order = ["/"]
        home = self.docs / "index.html"
        if home.exists():
            doc = pg.Doc(home.read_text(encoding="utf-8"))
            nav = doc.find(lambda n: n.tag == "nav")
            if nav is not None:
                for a in nav.descendants():
                    href = a.attr("href") or ""
                    if a.tag == "a" and href in found and href not in order:
                        found[href] = doc.text_of(a) or found[href]
                        order.append(href)
        order += [p for p in found if p not in order]
        return [{"path": p, "label": found[p]} for p in order]

    def page_file(self, path: str) -> Path:
        if not re.fullmatch(r"/(?:[a-z0-9-]+/)*", path or ""):
            raise ApiError("not a page: %s" % path)
        f = (self.docs / path.lstrip("/") / "index.html").resolve()
        if self.docs not in f.parents or not f.exists():
            raise ApiError("no such page: %s" % path)
        return f

    def rel(self, f: Path) -> str:
        return str(f.relative_to(self.root))

    def page_info(self, path: str) -> dict:
        f = self.page_file(path)
        doc = pg.Doc(f.read_text(encoding="utf-8"))
        info = doc.summary()
        info.update({"path": path, "file": self.rel(f)})
        return info

    def annotated(self, f: Path) -> str:
        """The page as served to the preview: annotated, with the overlay script before </body>."""
        text = pg.Doc(f.read_text(encoding="utf-8")).annotated()
        tag = '<script src="/__editor/overlay.js"></script>\n'
        return text.replace("</body>", tag + "</body>", 1) if "</body>" in text else text + tag

    # --- edits ---------------------------------------------------------------------------------

    def same_elsewhere(self, path: str, index: int) -> List[dict]:
        """Other pages with the same element in the same place, saying the same thing: the header, the
        footer, the closing call to action."""
        return self._same_in_others(self.page_file(path).read_text(encoding="utf-8"), index, path)

    def _same_in_others(self, text: str, index: int, path: str) -> List[dict]:
        doc = pg.Doc(text)
        if not 0 <= index < len(doc.editables):
            raise ApiError("that element is not on the page any more; reload the preview")
        n = doc.editables[index]
        loc, wanted = doc.locator(n), doc.text_of(n)
        out = []
        for p in self.pages():
            if p["path"] == path:
                continue
            d2 = pg.Doc(self.page_file(p["path"]).read_text(encoding="utf-8"))
            m = d2.resolve(loc)
            if m is None or m.tag != n.tag or d2.text_of(m) != wanted:
                continue
            idx = d2.editable_index(m)
            if idx is not None:
                out.append({"path": p["path"], "label": p["label"], "index": idx})
        return out

    def set_text(self, path: str, index: int, before: str, after: str, everywhere: bool) -> dict:
        f = self.page_file(path)
        text = f.read_text(encoding="utf-8")
        others = self._same_in_others(text, index, path) if everywhere else []   # before the page changes
        new = pg.set_text(text, index, before, after)
        changed, skipped = [], []
        if new != text:
            f.write_text(new, encoding="utf-8")
            changed.append(self.rel(f))
        for other in others:
            g = self.page_file(other["path"])
            g_text = g.read_text(encoding="utf-8")
            d2 = pg.Doc(g_text)
            cur = d2.inner(d2.editables[other["index"]])
            adapted = pg.retarget(before, after, cur)
            if adapted is None:
                skipped.append({"file": self.rel(g), "reason": "marked up differently there"})
                continue
            try:
                g.write_text(pg.set_text(g_text, other["index"], cur, adapted), encoding="utf-8")
                changed.append(self.rel(g))
            except pg.EditError as e:
                skipped.append({"file": self.rel(g), "reason": str(e)})
        return {"changed": changed, "skipped": skipped}

    def section(self, path: str, index: int, action: str) -> dict:
        f = self.page_file(path)
        text = f.read_text(encoding="utf-8")
        if action == "hide":
            new = pg.set_hidden(text, index, True)
        elif action == "show":
            new = pg.set_hidden(text, index, False)
        elif action == "up":
            new = pg.move_section(text, index, -1)
        elif action == "down":
            new = pg.move_section(text, index, +1)
        else:
            raise ApiError("unknown action %r" % action)
        if new != text:
            f.write_text(new, encoding="utf-8")
        return self.page_info(path)

    def tokens(self) -> List[dict]:
        return tk.read_tokens(self.css.read_text(encoding="utf-8"))

    def set_tokens(self, values: Dict[str, str]) -> List[dict]:
        css = self.css.read_text(encoding="utf-8")
        new = tk.set_tokens(css, values)
        if new != css:
            self.css.write_text(new, encoding="utf-8")
        return self.tokens()

    # --- git -----------------------------------------------------------------------------------

    def git(self, *args: str, check: bool = True) -> str:
        r = subprocess.run(["git", *args], cwd=str(self.root), capture_output=True, text=True, timeout=120)
        if check and r.returncode != 0:
            raise ApiError((r.stderr or r.stdout).strip() or "git %s failed" % args[0])
        return r.stdout

    def branch(self) -> str:
        return self.git("rev-parse", "--abbrev-ref", "HEAD").strip()

    def _branch_exists(self, name: str) -> bool:
        r = subprocess.run(["git", "show-ref", "--verify", "--quiet", "refs/heads/" + name], cwd=str(self.root))
        return r.returncode == 0

    def status(self) -> dict:
        changed = [l[3:] for l in self.git("status", "--short", "--", "docs").splitlines() if l.strip()]
        return {"branch": self.branch(), "changed": changed}

    def diff(self) -> dict:
        return {"stat": self.git("diff", "--stat=52,34", "--", "docs"), "diff": self.git("diff", "--", "docs"),
                **self.status()}

    def discard(self) -> dict:
        self.git("checkout", "--", "docs")
        return self.status()

    def commit(self, message: str) -> dict:
        message = (message or "").strip()
        if not message:
            raise ApiError("say what changed; that line becomes the commit message")
        if not self.status()["changed"]:
            raise ApiError("nothing to commit")
        branch = self.branch()
        if branch in ("main", "master"):                 # never commit to main: a branch named by the day
            base = "edit/%s" % dt.date.today().isoformat()
            branch, n = base, 1
            while self._branch_exists(branch):
                n += 1
                branch = "%s-%d" % (base, n)
            self.git("checkout", "-b", branch)
        self.git("add", "-A", "--", "docs")
        self.git("commit", "-m", message)
        return {"branch": branch, "sha": self.git("rev-parse", "--short", "HEAD").strip(), "subject": message}

    def publish(self) -> dict:
        """Push the branch and open a pull request. Merging stays on GitHub, as it always has."""
        branch = self.branch()
        if branch in ("main", "master"):
            raise ApiError("commit first; the editor never pushes main")
        if self.status()["changed"]:
            raise ApiError("there are uncommitted changes; commit or discard them first")
        self.git("push", "-u", "origin", branch)
        view = subprocess.run(["gh", "pr", "view", branch, "--json", "url", "-q", ".url"], cwd=str(self.root),
                              capture_output=True, text=True, timeout=120)
        if view.returncode == 0 and view.stdout.strip():
            return {"url": view.stdout.strip(), "branch": branch, "existing": True}
        create = subprocess.run(["gh", "pr", "create", "--fill", "--head", branch], cwd=str(self.root),
                                capture_output=True, text=True, timeout=120)
        if create.returncode != 0:
            raise ApiError((create.stderr or create.stdout).strip() or "gh pr create failed")
        m = re.search(r"https://github\.com/\S+", create.stdout + create.stderr)
        return {"url": m.group(0) if m else "", "branch": branch, "existing": False}


class Handler(BaseHTTPRequestHandler):
    site: Site = None  # type: ignore[assignment]
    server_version = "foundate-editor/1"

    def log_message(self, fmt, *args):           # quiet unless asked
        if self.server.verbose:                  # type: ignore[attr-defined]
            super().log_message(fmt, *args)

    # --- helpers -------------------------------------------------------------------------------

    def _json(self, obj, code: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _bytes(self, data: bytes, ctype: str, code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _file(self, f: Path) -> None:
        ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self._bytes(f.read_bytes(), ctype)

    def _same_origin(self) -> bool:
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin") or ""
        referer = self.headers.get("Referer") or ""
        allowed = {"http://" + host, "http://127.0.0.1:%d" % self.server.server_port,   # type: ignore[attr-defined]
                   "http://localhost:%d" % self.server.server_port}                      # type: ignore[attr-defined]
        if origin:
            return origin in allowed
        return any(referer.startswith(a + "/") for a in allowed)

    # --- routes --------------------------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        url = urlsplit(self.path)
        path = unquote(url.path)
        q = parse_qs(url.query)
        try:
            if path == "/__editor" or path == "/__editor/":
                return self._file(UI / "index.html")
            if path.startswith("/__editor/"):
                f = (UI / path[len("/__editor/"):]).resolve()
                if UI not in f.parents or not f.is_file():
                    return self._json({"error": "not found"}, 404)
                return self._file(f)
            if path.startswith("/__api/"):
                return self._api_get(path[len("/__api/"):], q)
            return self._static(path, edit="__edit" in q)
        except (ApiError, pg.EditError, tk.TokenError) as e:
            self._json({"error": str(e)}, 400)

    def do_HEAD(self) -> None:  # noqa: N802
        """Health checks only (the desktop app sends one); nothing is served without a GET."""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        url = urlsplit(self.path)
        if not url.path.startswith("/__api/"):
            return self._json({"error": "not found"}, 404)
        if not self._same_origin():
            return self._json({"error": "cross-origin write refused"}, 403)
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            self._api_post(url.path[len("/__api/"):], body)
        except (ApiError, pg.EditError, tk.TokenError, ValueError, KeyError, TypeError) as e:
            self._json({"error": str(e) or e.__class__.__name__}, 400)

    def _static(self, path: str, edit: bool) -> None:
        docs = self.site.docs
        if path.endswith("/"):
            path += "index.html"
        f = (docs / path.lstrip("/")).resolve()
        if docs not in f.parents and f != docs:
            return self._json({"error": "not found"}, 404)
        if f.is_dir():                                   # /work -> /work/
            self.send_response(301)
            self.send_header("Location", path + "/")
            self.end_headers()
            return
        if not f.is_file():
            nf = docs / "404.html"
            return self._bytes(nf.read_bytes(), "text/html; charset=utf-8", 404) if nf.exists() \
                else self._json({"error": "not found"}, 404)
        if edit and f.suffix == ".html":
            return self._bytes(self.site.annotated(f).encode("utf-8"), "text/html; charset=utf-8")
        self._file(f)

    def _api_get(self, name: str, q: Dict[str, List[str]]) -> None:
        s = self.site
        if name == "state":
            return self._json({"pages": s.pages(), "tokens": s.tokens(), **s.status()})
        if name == "page":
            return self._json(s.page_info(q.get("path", ["/"])[0]))
        if name == "same":
            return self._json({"pages": s.same_elsewhere(q.get("path", ["/"])[0], int(q.get("index", ["-1"])[0]))})
        if name == "diff":
            return self._json(s.diff())
        self._json({"error": "not found"}, 404)

    def _api_post(self, name: str, b: dict) -> None:
        s = self.site
        if name == "text":
            return self._json(s.set_text(b["path"], int(b["index"]), str(b["before"]), str(b["after"]),
                                         bool(b.get("everywhere"))))
        if name == "section":
            return self._json(s.section(b["path"], int(b["index"]), str(b["action"])))
        if name == "tokens":
            values = b.get("values") or {}
            if not isinstance(values, dict):
                raise ApiError("values must be an object")
            return self._json({"tokens": s.set_tokens({str(k): str(v) for k, v in values.items()})})
        if name == "discard":
            return self._json(s.discard())
        if name == "commit":
            return self._json(s.commit(str(b.get("message", ""))))
        if name == "publish":
            return self._json(s.publish())
        self._json({"error": "not found"}, 404)


def make_server(root: Path, port: int, verbose: bool = False) -> ThreadingHTTPServer:
    Handler.site = Site(root)
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    srv.verbose = verbose                     # type: ignore[attr-defined]
    return srv


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(HERE.parent.parent), help="the website checkout (default: this repo)")
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--verbose", action="store_true", help="log every request")
    a = ap.parse_args(argv)
    srv = make_server(Path(a.root), a.port, a.verbose)
    print("foundate editor: http://127.0.0.1:%d/__editor/  (editing %s)" % (a.port, Handler.site.root), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
