# Launch runbook: moving foundate.ai to GitHub Pages

One-time cutover from the previous host (OpenAI Sites, owner-private) to
GitHub Pages. Delete this file once the site has been live on GitHub Pages
for a while and nothing here is still open.

## State on 2026-10-09

- Staging is live at <https://a-petty.github.io/foundate-website/> (same files as `main`).
- `https://foundate.ai` and `https://www.foundate.ai` still point at the old host and answer **401** to the public.
- Google Workspace mail on the domain is fully configured and must survive the cutover untouched.
- Cutover is waiting on the owner's go-ahead.

### DNS snapshot before cutover (public resolver, 2026-10-09)

| Type | Host | Value | Group |
| --- | --- | --- | --- |
| NS | `@` | `pdns1.registrar-servers.com.`, `pdns2.registrar-servers.com.` | Namecheap, unchanged |
| A | `@` | `162.159.143.30` | **website, old host** |
| A | `@` | `172.66.3.26` | **website, old host** |
| CNAME | `www` | `custom-domains.chatgpt.site.` | **website, old host** |
| TXT | `_openai-site-verification` | `openai-site-verification=qN61…` | **website, old host** |
| TXT | `_openai-site-verification.www` | `openai-site-verification=urmr…` | **website, old host** |
| TXT | `_cf-custom-hostname` | `c4fb5ec5-983b-4332-8958-6cd614825137` | **website, old host** |
| TXT | `_cf-custom-hostname.www` | `7c34062d-db93-49f3-8378-b5db4192ba7b` | **website, old host** |
| MX | `@` | `1 smtp.google.com.` | Google Workspace, keep |
| TXT | `@` | `v=spf1 include:_spf.google.com ~all` | Google Workspace, keep |
| TXT | `@` | `google-site-verification=RJyeN7…` | Google Workspace, keep |
| TXT | `@` | `anthropic-domain-verification-9c08g8=…` | Anthropic domain verification, keep |
| TXT | `google._domainkey` | `v=DKIM1;k=rsa;p=MIIBIjAN…` (2048-bit) | Google Workspace, keep |
| TXT | `_dmarc` | *(none yet)* | see open items |

## Cutover steps

Namecheap: Domain List → Manage `foundate.ai` → Advanced DNS → Host Records.
Host values are relative to `foundate.ai`; do not append the domain.

**1. Delete the seven old-host website records** (the rows marked *website, old host* above): both `@` A records, the `www` CNAME, and the four `_openai-site-verification*` / `_cf-custom-hostname*` TXT records.

**2. Add the GitHub Pages records** (TTL Automatic is fine):

| Type | Host | Value |
| --- | --- | --- |
| A | `@` | `185.199.108.153` |
| A | `@` | `185.199.109.153` |
| A | `@` | `185.199.110.153` |
| A | `@` | `185.199.111.153` |
| AAAA | `@` | `2606:50c0:8000::153` |
| AAAA | `@` | `2606:50c0:8001::153` |
| AAAA | `@` | `2606:50c0:8002::153` |
| AAAA | `@` | `2606:50c0:8003::153` |
| CNAME | `www` | `a-petty.github.io.` |

**3. Leave every other record alone**: MX, the three `@` TXT records (SPF, Google verification, Anthropic verification) and `google._domainkey`.

**4. Attach the domain to the repo** (from `~/Dev/Foundate/website`, after DNS is saved):

```sh
printf 'foundate.ai\n' > CNAME && git add CNAME && git commit -m "Attach custom domain" && git push
gh api -X PUT repos/a-petty/foundate-website/pages -f cname=foundate.ai
```

GitHub then checks DNS and requests a certificate from Let's Encrypt. That
usually takes a few minutes, occasionally up to an hour. Watch it with:

```sh
gh api repos/a-petty/foundate-website/pages --jq '{cname, status, https_certificate: .https_certificate.state, protected_domain_state}'
```

**5. Once the certificate state is `approved`, enforce HTTPS:**

```sh
gh api -X PUT repos/a-petty/foundate-website/pages -F https_enforced=true
```

**6. Verify** (each should hold from any network once caches expire; the old
records had TTL 60 so it is quick):

```sh
curl -sI https://foundate.ai/ | head -1            # HTTP/2 200
curl -sI https://www.foundate.ai/ | head -1        # 301 → https://foundate.ai/
curl -sI http://foundate.ai/ | head -1             # 301 → https
curl -sI https://a-petty.github.io/foundate-website/ | head -1   # 301 → https://foundate.ai/
curl -sI https://foundate.ai/assets/og-image.jpg | head -1       # 200
```

Then open <https://foundate.ai> in a browser, click through the nav anchors
and the contact link, and paste the URL into Slack or iMessage to confirm the
social preview renders.

## After launch

- **Verify the domain on the GitHub account** so nobody else can claim it on
  GitHub Pages if the repo is ever removed: GitHub → Settings → Pages →
  *Verified domains* → add `foundate.ai`, then add the TXT record it gives you
  (`_github-pages-challenge-a-petty`) at Namecheap.
- **Retire the old host.** Delete the OpenAI Sites project from the ChatGPT
  account that created it. The DNS records for it are already gone after step 1.
- **DMARC.** Mail is authenticated (SPF + DKIM) but has no policy record.
  Suggested first record, monitoring only:
  `TXT _dmarc "v=DMARC1; p=none; rua=mailto:alexander@foundate.ai"`.
  Tighten to `p=quarantine` after a few weeks of clean reports.
- **Search Console** (optional): add the property and submit `https://foundate.ai/sitemap.xml`.

## Open items not covered by this runbook

- A copy change was paused before the hosting move: reframing the two
  featured "Being finalized" projects (AI Chief of Staff, reporting automation
  hub) as completed. It has **not** been applied; the page still says
  "What we're building". This is the owner's call and is a normal edit-and-push
  once decided.
- No analytics and no contact form on the site today. Both are deliberate
  omissions for launch, not oversights.
