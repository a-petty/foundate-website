# foundate.ai

The Foundate AI website. One static page: no build step, no JavaScript, no
third-party services. Pushing to `main` publishes it.

## Layout

| Path | What it is |
| --- | --- |
| `index.html`, `styles.css` | The page. Copy edits happen in `index.html`. |
| `assets/foundations.webp`, `assets/foundations.jpg` | Hero artwork (WebP, with a JPEG fallback). |
| `assets/og-image.jpg` | 1200×630 social preview used by LinkedIn, Slack, iMessage, etc. |
| `assets/apple-touch-icon.png`, `assets/favicon-32.png`, `assets/icon-*.png` | Icons. The SVG favicon is inline in `index.html`. |
| `404.html` | Not-found page. Self-contained so it renders at any path. |
| `robots.txt`, `sitemap.xml`, `manifest.webmanifest` | Crawler and install metadata. |
| `tools/make_images.py` | Regenerates every derived image from the source hero PNG. |
| `.nojekyll` | Tells GitHub Pages to serve the files exactly as committed. |

## Edit and publish

1. Edit the files in `~/Dev/Foundate/website` (a Claude Code session or any editor).
2. Preview locally:

   ```sh
   python3 -m http.server 8765 --bind 127.0.0.1
   ```

   then open <http://127.0.0.1:8765/>. Check desktop and a ~390px-wide
   viewport; the page has no horizontal scroll at either.
3. Commit with a message that says what changed in the copy or design, then
   `git push`. GitHub Pages rebuilds within about a minute.

Every published state of the site is a commit, so `git log` is the site's
change history. There is nothing to roll back except `git revert`.

When the hero artwork changes, drop the new source PNG anywhere and run:

```sh
uv run --with pillow python -I tools/make_images.py path/to/source.png assets/
```

It rewrites the WebP, JPEG, social preview and icons in one pass.

## Hosting

GitHub Pages, served from the `main` branch root of `a-petty/foundate-website`.

- Staging URL: <https://a-petty.github.io/foundate-website/>. Once the custom
  domain is attached, GitHub redirects this URL to `https://foundate.ai/`.
- Production: `https://foundate.ai/` and `https://www.foundate.ai/`, with the
  certificate issued and renewed by GitHub.
- No analytics, no contact form; the contact link is `mailto:alexander@foundate.ai`.

## DNS

The domain is registered at Namecheap and uses Namecheap's nameservers. The
zone carries two unrelated groups of records; only the website group changes
when the site moves hosts.

**Website records** (point at the current host):

| Type | Host | Value |
| --- | --- | --- |
| A ×4 | `@` | `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153` |
| AAAA ×4 | `@` | `2606:50c0:8000::153`, `2606:50c0:8001::153`, `2606:50c0:8002::153`, `2606:50c0:8003::153` |
| CNAME | `www` | `a-petty.github.io.` |
| TXT | `_github-pages-challenge-a-petty` | Issued by GitHub when the domain is verified on the account. |

**Google Workspace records** (never touch these when changing the website):

| Type | Host | Purpose |
| --- | --- | --- |
| MX | `@` | `1 smtp.google.com.` |
| TXT | `@` | `v=spf1 include:_spf.google.com ~all` |
| TXT | `@` | `google-site-verification=…` |
| TXT | `google._domainkey` | DKIM public key |
| TXT | `_dmarc` | DMARC policy (once configured) |

See `LAUNCH.md` for the one-time cutover from the previous host.
