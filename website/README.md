# Website

The Distilled marketing website — static pages built with [Eleventy](https://www.11ty.dev/).

## Structure

```
website/
  src/
    _includes/
      base.njk      # shared HTML shell: nav, footer, shared CSS, mobile menu JS
      legal.njk     # legal page layout (extends base, adds legal-specific CSS)
    index.njk       # homepage
    privacy.njk     # privacy policy
    terms.njk       # website terms of use
    app-terms.njk   # application terms and conditions
    getting-started.njk  # setup guide
    images/         # static assets (copied as-is to output)
  test/
    routing.test.mjs     # URL contract tests, run against the real Caddyfile
  .eleventy.js      # Eleventy config
  Caddyfile         # how the built site is served — the URL contract
  package.json
  _site/            # compiled output (gitignored)
```

## Commands

All commands are available from the repo root via `make`:

```bash
make website-build     # compile to website/_site/
make website-serve     # local dev server with live reload at localhost:8080
make website-test      # build, then test the URL contract (needs caddy on PATH)
```

Or directly from this directory:

```bash
npm install            # install dependencies
npm run build          # compile to _site/
npm run serve          # local dev server with live reload
npm test               # build, then run the routing tests
```

## Adding a page

1. Create `src/your-page.njk` with front matter and a `{% block %}`. The
   `permalink` keeps the `.html` extension — that is the file on disk, not the
   URL the page is served at (see "URLs" below):

```nunjucks
---
title: Page Title — Distilled
description: Page description.
permalink: /your-page.html
---
{% extends "legal.njk" %}

{% block article %}
<h1>Page Title</h1>
...
{% endblock %}
```

2. Add a link to it in the footer inside `src/_includes/base.njk`, using the
   canonical extensionless URL (`/your-page`, not `/your-page.html`).
3. Run `make website-test` to verify the output and its URLs.

Use `{% extends "base.njk" %}` instead of `legal.njk` if the page needs a custom layout rather than the standard legal article format.

## URLs

Pages are served at extensionless URLs — `/terms`, not `/terms.html`. The build
emits flat `terms.html` files and `Caddyfile` maps between the two:

| URL              | Response                                    |
| ---------------- | ------------------------------------------- |
| `/terms`         | 200, served from `_site/terms.html`         |
| `/terms.html`    | 301 → `/terms` (query string preserved)     |
| `/index.html`    | 301 → `/`                                   |
| `/no-such-page`  | 404 — there is no homepage fallback         |

That contract predates the container: it is what Cloudflare Pages served, so it
is what search engines index and what browsers have cached 301s for. Always
link to the canonical form. `test/routing.test.mjs` boots the real Caddyfile
over a real build and asserts the table above — see
[ADR 006](../docs/adrs/006-website-url-canonicalisation.md).

Running the tests needs the `caddy` binary on `PATH` (or `CADDY_BIN` pointing
at it); CI installs it for the `test-website` job.

## Deployment

The build output is plain HTML with no runtime dependencies, so `_site/` can be
served by any static host.

### Analytics

Setting `POSTHOG_KEY` at build time embeds the PostHog web analytics snippet in
every page. Events go to `https://d.distilledmetrics.com`, a managed PostHog
reverse proxy, so that content blockers and tracking protection do not silently
drop them; `POSTHOG_HOST` and `POSTHOG_UI_HOST` override that. The snippet runs
in PostHog's cookieless mode — anonymous, nothing stored on the visitor's device
— so no consent banner is required. Without `POSTHOG_KEY` the build ships no
analytics at all. See [docs/analytics.md](../docs/analytics.md) and
[ADR 007](../docs/adrs/007-posthog-reverse-proxy.md).

`Dockerfile` packages that for container hosts: a Node stage runs `npm run build`,
then the output is copied into a `caddy:2-alpine` stage that serves it on `$PORT`
using `Caddyfile`. There is deliberately no SPA history fallback — a missing page
must 404 rather than render the homepage under the wrong URL.

Build and run it locally with:

```bash
docker build -t distilled-website --build-arg POSTHOG_KEY=phc_... .
docker run --rm -e PORT=8080 -p 8080:8080 distilled-website
```
