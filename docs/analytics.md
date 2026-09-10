# Analytics

Distilled uses [PostHog](https://posthog.com) for product analytics (the client
application) and web analytics (the marketing website). Both are configured to
be **anonymous and cookieless**, so no cookie consent banner is required.

## How it stays cookieless

Both surfaces initialise PostHog with `cookieless_mode: "always"`, which uses
PostHog's [cookieless server hash mode](https://posthog.com/docs/tutorials/cookieless-tracking):

- **Nothing is stored on the visitor's device** — no cookies, no localStorage,
  no sessionStorage. Under UK PECR, this removes the requirement for a consent
  banner (only device storage/access triggers it).
- **Users are counted via a privacy-preserving server-side hash** (salted daily),
  so unique-visitor counts stay approximately correct without any identifier
  persisting on the device.
- **`identify()` is never called** and must not be added while this mode is on
  (PostHog disallows it in cookieless mode). All events are anonymous — no
  linking of analytics events to Clerk accounts.

If we ever want identified product analytics, that is a privacy-posture change:
it requires a consent flow, a different PostHog configuration, and a privacy
policy update. Raise an RFC first.

## Reverse proxy

Both surfaces send events to **`https://d.distilledmetrics.com`**, a managed
PostHog reverse proxy (a CNAME onto PostHog's EU infrastructure), rather than
straight to `https://eu.i.posthog.com`.

PostHog's own domains are on the default block lists shipped with uBlock Origin,
AdGuard, Brave, and Safari and Firefox tracking protection, so a large share of
requests never leaves the browser — silently, since `posthog-js` cannot see a
request blocked at the network layer. Sending to a first-party domain avoids
that. See [ADR 007](adrs/007-posthog-reverse-proxy.md) for the full rationale,
including why this is compatible with the privacy posture.

Because `api_host` is no longer a PostHog domain, **`ui_host` must be set** to
`https://eu.posthog.com`, otherwise links the SDK generates (toolbar, session
links) point at the proxy.

Nothing about what is collected, who processes it, or where it is stored
changes — the proxy terminates on PostHog's EU infrastructure.

## Setup

Both surfaces expect a **PostHog EU Cloud** project, consistent with the privacy
policy, which states analytics data is hosted in the EU.

One-time manual steps in PostHog:

1. Create the project in the **EU** region.
2. In **Project settings**, enable **Cookieless server hash mode** — without
   this, events sent in cookieless mode are rejected.
3. Enable **Web analytics** for the site domain if you want the web analytics
   dashboard.
4. Set up the **managed reverse proxy** and point a CNAME at it. The proxy must
   serve every path the SDK uses, including `/e/`, `/i/v0/e/`, `/batch/`,
   `/flags/`, `/array/` and `/static/` — PostHog's managed proxy does.

### Client (product analytics)

`client/src/lib/analytics.ts` initialises `posthog-js` from `main.tsx`.
Configuration comes from Vite env vars (build-time):

| Variable | Purpose |
| --- | --- |
| `VITE_POSTHOG_KEY` | Project API key. Analytics is entirely off when unset. |
| `VITE_POSTHOG_HOST` | API host; defaults to `https://d.distilledmetrics.com`. |

`ui_host` is a constant in `analytics.ts` rather than an env var — it tracks the
PostHog region, which the privacy policy already fixes to the EU.

For container builds, pass them as `--build-arg`s (see `client/Dockerfile`).
Pageviews and page-leaves are captured automatically, including SPA route
changes (via the `defaults: "2026-05-30"` preset's history instrumentation).

### Website (web analytics)

The Eleventy build embeds the PostHog snippet in `website/src/_includes/base.njk`
when `POSTHOG_KEY` is set at build time (`website/.eleventy.js` exposes it as
global data). Without the env var, the built site contains no analytics code.

| Variable | Purpose |
| --- | --- |
| `POSTHOG_KEY` | Project API key. Snippet omitted when unset. |
| `POSTHOG_HOST` | API host; defaults to `https://d.distilledmetrics.com`. |
| `POSTHOG_UI_HOST` | PostHog app host for SDK-generated links; defaults to `https://eu.posthog.com`. |

For container builds: `docker build --build-arg POSTHOG_KEY=phc_... .`

The inline snippet is the one PostHog's dashboard generates. It is a stub that
queues calls until `array.js` loads from `POSTHOG_HOST`, so it has to be
replaced wholesale (not hand-edited) when PostHog updates it — the method list
inside it has to match the SDK version being loaded.

## Privacy policy

The privacy policy (`website/src/privacy.njk`) discloses PostHog as an
anonymised, EU-hosted analytics processor and explains the cookieless approach
(sections 2, 5, and 8). Any change to what analytics collects must be reflected
there, and the effective date bumped.
