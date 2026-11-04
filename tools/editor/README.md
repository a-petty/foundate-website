# The local editor

A panel for changing foundate.ai without editing HTML by hand: the design tokens with a live
preview, the text of any element in place, and which sections show and in what order. It runs on
your Mac only and writes ordinary edits into `docs/`, so `git diff` shows exactly what changed and
the usual branch, pull request and merge flow publishes it. Nothing about the published site changes:
no script, no build step, no service.

Built 2026-10-30 from the idea that tweaking a site by prompting ("a darker green", "hide that
section") is slower than having the controls yourself.

## Run it

```sh
python3 tools/editor/serve.py
```

then open <http://127.0.0.1:8766/__editor/>. In Claude Code the `editor` configuration in
`.claude/launch.json` starts the same thing. It needs only Python 3.9 or later, which macOS ships;
on Windows, in PowerShell, it is `python tools\editor\serve.py` (or `py` if `python` is not on the
path). Files keep whatever line endings they were checked out with.

## What it does

- **Page.** Pick a page. The list shows every top-level section plus the header and footer. ● hides
  a section and ◌ shows it again; the arrows reorder. A hidden section keeps its place in the file
  with a `hidden` attribute, so nothing is deleted and anything can come back later. Clicking a
  section's name scrolls the preview to it.
- **Text.** Click any text in the preview and type. Enter saves, Escape cancels, pasting is plain
  text. The same element can be edited in the panel's text box, markup included. Emptying an element and pressing Enter removes it (after a confirmation), and the panel's Move up, Move down and Remove buttons do the same for the selected element; a removed element takes its line with it, so no blank line is left behind, and a wrapper it leaves empty (a belief's column, say) goes with it, up to but never including a section, the header or the footer. When the same
  element says the same thing on other pages (the header, the footer, the closing call to action),
  the panel offers to change them all; each page keeps its own attributes, such as the current-page
  marker on a nav link.
- **Design.** Every `--token` in the `:root` block of `docs/styles.css`, as a colour picker, a
  slider, or the three numbers of a `clamp(min, vw, max)`. Changes preview as you type; Save writes
  them to the stylesheet; Reset drops them. "used N×" is how many rules read the token.
- **Viewport.** Desktop, laptop (1024), tablet (768) and phone (390) widths for the preview.
- **Changes.** The diff since the last commit. Commit, with a message (on a branch named
  `edit/<date>` when you are on main). Discard, which throws away every uncommitted change in
  `docs/`. Push and open a pull request, which does exactly that; merging on GitHub is what
  publishes, as before.

## How it writes

The pages are hand-written HTML and GitHub Pages serves them as committed, so the editor never
rewrites a file through a DOM, which would reflow every line. `pages.py` parses a page into a tree
that records where each element starts and ends in the source. A text edit replaces exactly the
inner span of one element, keeping its indentation. Hiding adds or removes one attribute in one
start tag. Moving swaps two whole sections. `tokens.py` changes only the value on a token's own
line. Anything that does not line up exactly (the file changed since the preview loaded, markup that
is not inline, an unknown token, an empty text) is refused with a message, never guessed.

Local only: the server binds 127.0.0.1, writes need a same-origin request, and `tools/` is outside
`docs/`, so none of this is ever served from foundate.ai. The preview page gets `data-ed` markers
and the overlay script injected in memory only when loaded with `?__edit=1`; the files on disk never
carry them.

## What it does not do

- Add sections, images or pages. That is still a Claude Code session or a text editor, and the
  claims register in `~/Dev/Foundate/design/` still governs what the copy may say.
- Touch anything outside `docs/`, push `main`, or merge.
- Delete. Hidden content stays in the public file; anyone reading the source can see it, so hide
  only what could be published.

## The rule that keeps it useful

When something new is added to the site, give the editor a handle on it:

- a colour or size that might be tuned later is a token in `:root`, not a literal inside a rule
  (`--hero-tint` exists because the hero's tint was the one green the picker could not reach);
- a block that might be hidden or reordered is a top-level `<section>` inside `<main>`, with
  `aria-labelledby` pointing at its heading, which is the name the panel shows.
- text someone else will write (a partner's bio, a new paragraph) is added on a branch with
  bracketed placeholder text, so they can replace it in place here and the branch's pull request
  carries their words; the placeholder never reaches `main`.

## Tests

```sh
uv run --with pytest python -m pytest tools/editor -q
```

They cover the parser's source positions, every edit's exactness and refusals, the token file, and
the HTTP API against a scratch copy of the real pages (text edits across pages, hide and move,
tokens, commit, discard, the cross-origin refusal). Nothing in the tests touches this checkout.
