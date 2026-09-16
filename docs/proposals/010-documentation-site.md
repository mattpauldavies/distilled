# Documentation Site

**Status:** Shipped

## Summary

Give the marketing website a documentation section at `/docs`, reachable from the top
navigation, and move the existing `/getting-started` guide into it. The guide had grown into
the only public explanation of how Distilled works — setup, metric definitions,
troubleshooting — on a single page with no room to add the rest (workspaces, team, repository
management, deployment vs release tracking, privacy). A section with one page per topic gives
each of those a URL that can be linked from the app, from support email, and from search.

## Goals

- One public home for product documentation, linked from the site's top navigation.
- A page per topic, each answering one question end to end.
- `/getting-started` keeps working — it is in the footer, in the app's onboarding screen, and
  indexed.
- No new build tooling: the same Eleventy build, the same Caddy URL contract.

## Non-goals

- Client-side search, versioning, or a docs CMS. Thirteen pages do not need any of it.
- Moving `docs/` (the repository's engineering documentation) onto the website. That folder
  is for people working on Distilled; `/docs` on the website is for people using it.
- API reference documentation. The API is not public yet.

## Design

### Structure

Pages live in `website/src/docs/`, one `.njk` file each, with the section index at
`website/src/docs.njk`. Front matter carries `navTitle` (the sidebar label), `order` (sidebar
position), and the usual `title`/`description`.

A directory data file (`website/src/docs/docs.11tydata.js`) gives every page in the folder the
`docs` tag and a `/docs/{{ page.fileSlug }}.html` permalink, so a new page is one file with no
registration step. `.eleventy.js` sorts the tagged pages into `collections.docs` by `order`,
and the layout renders the sidebar and the previous/next links from that collection — the
navigation cannot drift from the pages that exist.

### Layout

`website/src/_includes/docs.njk` extends `base.njk` and holds every style the documentation
pages use: the two-column shell with a sticky sidebar, the article typography, and the
callout, step-list and definition-row components the getting-started page already had. Pages
carry content only.

### URLs

The existing contract holds: the build emits flat `.html` files, Caddy serves them at
extensionless URLs. `_site/docs.html` is served at `/docs` and `_site/docs/metrics.html` at
`/docs/metrics` with no change to `try_files` — Caddy's file matcher ignores the `docs`
directory when resolving `/docs`, so the flat file wins. Two redirects are added:
`/getting-started` (and its `.html` form) to `/docs/getting-started`, preserving query
strings so campaign tags survive, and `/docs/` to `/docs` so the trailing-slash form does not
404.

## Decisions

**A section of pages, not a longer single page.** The getting-started guide was already at the
length where a reader scrolls past what they need. Separate URLs are what makes documentation
linkable from a support reply or an error state in the app.

**The sidebar is generated from the collection, not written by hand.** A hand-written list is
a second place to edit and the one that gets forgotten. The cost is that page order lives in
front matter rather than in one visible list.

**Redirect `/getting-started` rather than leaving a stub page.** A stub keeps two URLs alive
for the same content and splits the search ranking between them. The redirect is a 301, which
is what the rest of the site's moved URLs already use.

**Documentation duplicates the engineering docs rather than sharing a source.** `docs/metrics.md`
and `/docs/metrics` describe the same metrics for different readers — one states the
definition for someone changing the query, the other explains what the number means for
someone reading the dashboard. Generating one from the other would force a single voice on
both. The cost is real: a metric definition changes in two places, so
[docs/metrics.md](../metrics.md) and [docs/github-app.md](../github-app.md) name the website
pages that must move with them.

## Accepted consequences

- Thirteen documentation pages are prose about product behaviour, and prose goes stale when
  behaviour changes. The routing tests assert the pages exist and that their URLs resolve;
  nothing asserts they are still true.
- The site's CSS remains inline per layout. It is duplicated between `legal.njk` and
  `docs.njk` where they overlap, which is the existing trade: no build step for styles.

## Open items

- The GitHub App install link on `/docs/github-app` points at the app rather than at a
  marketplace listing, because installs must start inside Distilled to bind to a workspace.
  If a marketplace listing is added, that page needs revisiting.

## History

- Created when the documentation section was built, moving `/getting-started` into it.
