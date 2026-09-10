# ADR 006 — Website URL Canonicalisation

**Date:** 2026-09-10
**Status:** Accepted

## Context

The marketing website was originally hosted on Cloudflare Pages. Pages serves
static sites with "pretty" URLs: `_site/terms.html` is served at `/terms`, and
a request for `/terms.html` is answered with a permanent redirect to `/terms`.
Every page therefore had exactly one public URL, without an extension — and
that is the form search engines indexed and visitors bookmarked.

ADR 005 moved the site to a container (`website/Dockerfile`) serving the build
output with Caddy. The Caddyfile's `file_server` matches paths against files on
disk exactly, so the URL contract silently changed:

| URL            | Cloudflare Pages     | Caddy container |
| -------------- | -------------------- | --------------- |
| `/terms`       | 200                   | **404**         |
| `/terms.html`  | 301 → `/terms`        | 200             |

Every extensionless URL began to 404: indexed search results, bookmarks, and —
because browsers cache 301s indefinitely — the site's own footer links, which
are written as `/terms.html` but rewritten to `/terms` inside any browser that
visited the site while it was on Pages.

## Decision

**Extensionless URLs are the site's canonical form, and the serving layer
enforces that.** `website/Caddyfile`:

- resolves a canonical URL to the flat file the build emits, via
  `try_files {path} {path}.html`;
- permanently redirects the `.html` form to it, preserving the query string so
  campaign parameters survive the hop;
- redirects `/index.html` and `/index` to `/`.

Internal links (the site's own footer and body links, and the client's
onboarding link to the guide) point at the canonical form directly, so a click
never spends a redirect.

Eleventy still emits flat `terms.html` files rather than `terms/index.html`
directories: the mapping belongs in the server that already has to redirect the
legacy form, not in the build output.

`website/test/routing.test.mjs` boots the real Caddyfile over a real build and
asserts the whole contract — canonical URLs, redirects, assets, and the 404.
Its `SITE_ROOT` environment variable is the only concession the config makes to
being testable; the image still defaults to the `/srv` it copies the build into.

## Consequences

- The URL contract is the one that is already indexed and bookmarked, so the
  migration off Cloudflare Pages costs no traffic.
- Each page has exactly one 200-serving URL, so there is no duplicate content
  to canonicalise with `<link rel="canonical">` tags.
- A missing page still 404s — the redirects are pattern-based, not a fallback.
- The serving layer now has behaviour worth testing, and a `test-website` CI
  job that installs Caddy and tests it.
- Any future host must provide the same two behaviours (extensionless
  resolution and the `.html` redirect) or reintroduce the same 404s.
