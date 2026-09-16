# Website

The Distilled marketing website — static pages built with [Eleventy](https://www.11ty.dev/).

## Structure

```
website/
  src/
    _includes/
      base.njk      # shared HTML shell: nav, footer, shared CSS, mobile menu JS
      legal.njk     # legal page layout (extends base, adds legal-specific CSS)
      docs.njk      # documentation layout (sidebar, article styles, prev/next)
    index.njk       # homepage
    privacy.njk     # privacy policy
    terms.njk       # website terms of use
    app-terms.njk   # application terms and conditions
    docs.njk        # documentation index, served at /docs
    docs/           # documentation pages, served at /docs/<name>
      docs.11tydata.js  # tags + permalink applied to every page in the folder
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

## Adding a documentation page

Documentation pages live in `src/docs/` and are the public product docs served
at `/docs`. Adding one is a single file — `docs.11tydata.js` gives every page in
the folder its `docs` tag and its permalink, and the sidebar and previous/next
links are generated from that collection, so there is no navigation list to
update:

```nunjucks
---
title: Page Title — Distilled
description: One sentence, used as the meta description.
navTitle: Sidebar label
summary: One line, shown on the /docs index card.
order: 14
eyebrow: Reference
heading: The headline shown on the page
lead: The standfirst under the headline.
---
{% extends "docs.njk" %}

{% block doc %}
<section id="something">
  <h2>Something</h2>
  <p>...</p>
</section>
{% endblock %}
```

`order` sets the position in the sidebar and the reading order the previous/next
links follow. The layout provides `.callout`, `.docs-steps` / `.docs-step`,
`.docs-rows` / `.docs-row`, `.docs-cards` / `.docs-card` and `.docs-table-wrap`;
pages carry content only, never their own `<style>` block.

Then run `make website-test` — the routing tests walk every page listed on the
`/docs` index and assert it serves.

## URLs

Pages are served at extensionless URLs — `/terms`, not `/terms.html`. The build
emits flat `terms.html` files and `Caddyfile` maps between the two:

| URL                 | Response                                        |
| ------------------- | ----------------------------------------------- |
| `/terms`            | 200, served from `_site/terms.html`             |
| `/terms.html`       | 301 → `/terms` (query string preserved)         |
| `/index.html`       | 301 → `/`                                       |
| `/docs`             | 200, served from `_site/docs.html`              |
| `/docs/`            | 301 → `/docs`                                   |
| `/docs/metrics`     | 200, served from `_site/docs/metrics.html`      |
| `/getting-started`  | 301 → `/docs/getting-started` (the guide moved) |
| `/no-such-page`     | 404 — there is no homepage fallback             |

`/docs` resolves to the flat `docs.html` rather than the `docs/` directory
beside it: Caddy's file matcher skips directories, so `try_files` falls through
to the `.html` file. That is why the section index needs no directory index and
why `/docs/` is redirected rather than served.

That contract predates the container: it is what Cloudflare Pages served, so it
is what search engines index and what browsers have cached 301s for. Always
link to the canonical form. `test/routing.test.mjs` boots the real Caddyfile
over a real build and asserts the table above — see
[Proposal 007: Build and Deployment](../docs/proposals/007-build-and-deployment.md).

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
[Proposal 006: Observability](../docs/proposals/006-observability.md).

`Dockerfile` packages that for container hosts: a Node stage runs `npm run build`,
then the output is copied into a `caddy:2-alpine` stage that serves it on `$PORT`
using `Caddyfile`. There is deliberately no SPA history fallback — a missing page
must 404 rather than render the homepage under the wrong URL.

Build and run it locally with:

```bash
docker build -t distilled-website --build-arg POSTHOG_KEY=phc_... .
docker run --rm -e PORT=8080 -p 8080:8080 distilled-website
```
