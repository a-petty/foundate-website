# foundate.ai

The Foundate AI website. One static page: no build step, no JavaScript, no
third-party services. Pushing to `main` publishes it.

## Layout

GitHub Pages publishes only the `docs/` folder. Everything else in the repo
(this README, `LAUNCH.md`, `tools/`) stays in the repo and is not served.

| Path | What it is |
| --- | --- |
| `docs/index.html` | Home: hero, where the value is, two featured cases, ownership, contact. |
| `docs/work/index.html` | Work (foundate.ai/work/): every project with how it was proven. |
| `docs/how-we-work/index.html` | How we work (foundate.ai/how-we-work/): lessons, what you keep, where we build, engagements. |
| `docs/about/index.html` | About (foundate.ai/about/): why we exist, beliefs, how we are built, the two Managing Partners, the name. |
| `docs/styles.css` | All styles; design tokens at the top. |
| `docs/assets/fonts/` | Zilla Slab (headlines and wordmark), IBM Plex Sans (text, one variable file) and IBM Plex Mono (data), Latin subsets, self-hosted under the SIL Open Font License (`OFL.txt`). No third-party font service. |
| `docs/assets/hero.jpg` | Home-page hero: "Golden Gate Bridge and San Francisco skyline from Hawk Hill at Blue Hour" by Daniel L. Lu, Wikimedia Commons, CC BY-SA 4.0, extended about 10% at the top and bottom (edge rows stretched and blurred, no generated pixels). The footer carries the required credit, and this adaptation is itself CC BY-SA 4.0. |
| `docs/assets/og-image.jpg` | 1200×630 social preview used by LinkedIn, Slack, iMessage, etc. |
| `docs/assets/apple-touch-icon.png`, `favicon-32.png`, `icon-*.png` | Icons. The SVG favicon is inline in `index.html`. |
| `docs/404.html` | Not-found page. Self-contained so it renders at any path. |
| `docs/robots.txt`, `docs/sitemap.xml`, `docs/manifest.webmanifest` | Crawler and install metadata. |
| `docs/CNAME`, `docs/.nojekyll` | Custom domain, and "serve files exactly as committed". |
| `tools/make_images.py` | Draws the social preview and icons from the site fonts and the plinth-F mark. No source artwork. |

The header and footer are repeated in each page; change all four together.
Asset and page links are root-absolute (`/styles.css`, `/work/`).

Every claim on the page about past work must be supported by the claims
register that lives with the design source, outside this public repository.
Public copy uses generalized wording: no exact counts, client-identifying team
names or internal findings.

## Edit and publish

1. Edit the files in `~/Dev/Foundate/website` (a Claude Code session or any editor).
2. Preview locally:

   ```sh
   python3 -m http.server 8765 --bind 127.0.0.1 --directory docs
   ```

   then open <http://127.0.0.1:8765/>. Check desktop and a ~390px-wide
   viewport; the page has no horizontal scroll at either.
3. Commit with a message that says what changed in the copy or design, then
   `git push`. GitHub Pages rebuilds within about a minute.

Every published state of the site is a commit, so `git log` is the site's
change history. There is nothing to roll back except `git revert`.

When the social preview or icons need to change, edit `tools/make_images.py`
and run:

```sh
uv run --with pillow python -I tools/make_images.py docs/assets/fonts docs/assets/
```

The identity (deep green on warm paper, Zilla Slab, IBM Plex) was decided on
2026-10-09. Its design source, the comparison board and the decision record
live outside this public repo in `~/Dev/Foundate/design/`.

## Hosting

GitHub Pages, served from the `docs/` folder on the `main` branch of `a-petty/foundate-website`.

- Staging URL: <https://a-petty.github.io/foundate-website/>. Once the custom
  domain is attached, GitHub redirects this URL to `https://foundate.ai/`.
- Production: `https://foundate.ai/` and `https://www.foundate.ai/`, with the
  certificate issued and renewed by GitHub.
- No analytics, no contact form, no third-party requests; the contact link is `mailto:info@foundate.ai`.
- Changing the Pages source folder does not trigger a rebuild. After any
  change to Pages settings, request one:
  `gh api -X POST repos/a-petty/foundate-website/pages/builds`.
  Pages also caches pages for up to 10 minutes, so check with a `?x=…` query.

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
