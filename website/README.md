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
    images/         # static assets (copied as-is to output)
  .eleventy.js      # Eleventy config
  package.json
  _site/            # compiled output (gitignored)
```

## Commands

All commands are available from the repo root via `make`:

```bash
make website-build     # compile to website/_site/
make website-serve     # local dev server with live reload at localhost:8080
```

Or directly from this directory:

```bash
npm install            # install dependencies
npm run build          # compile to _site/
npm run serve          # local dev server with live reload
```

## Adding a page

1. Create `src/your-page.njk` with front matter and a `{% block %}`:

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

2. Add a link to it in the footer inside `src/_includes/base.njk`.
3. Run `make website-build` to verify the output.

Use `{% extends "base.njk" %}` instead of `legal.njk` if the page needs a custom layout rather than the standard legal article format.

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
[ADR 006](../docs/adrs/006-posthog-reverse-proxy.md).

`Dockerfile` packages that for container hosts: a Node stage runs `npm run build`,
then the output is copied into a `caddy:2-alpine` stage that serves it on `$PORT`
using `Caddyfile`. There is deliberately no SPA history fallback — a missing page
must 404 rather than render the homepage under the wrong URL.

Build and run it locally with:

```bash
docker build -t distilled-website --build-arg POSTHOG_KEY=phc_... .
docker run --rm -e PORT=8080 -p 8080:8080 distilled-website
```
