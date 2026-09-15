# Reliability Metrics via incident.io

**Status:** Proposed — not built
**Consolidates:** PRD 013 (reliability metrics)

## Summary

Add **change failure rate** and **time to restore service** by integrating with incident.io
as the source of truth for incidents. This completes the DORA four and, more importantly,
makes change failure rate defensible: incident-backed correlation rather than a proxy guess.

This is the only proposal in this folder that has not been implemented.

## Goals

- Accurate, incident-backed CFR and MTTR.
- Correlate incidents to deployments so every "failed deployment" can be explained.
- Keep setup low-effort: connect incident.io, then either auto-correlate or configure a
  minimal mapping.

## Non-goals

- Creating or updating incidents from Distilled. Read-only integration.
- Supporting other incident tools (PagerDuty, Opsgenie) in the same release.

## Definitions

**Time to restore service** — from the incident's `started_at` (falling back to `declared_at`,
then `created_at`) to `resolved_at` (falling back to `closed_at`). Aggregated as median and
P75 over the selected window. The fallback hierarchy must be disclosed in the UI, because
incident timestamps are inconsistent across organisations.

**Change failure rate** — a production deployment is considered failed if it is linked to an
incident meeting the configured severity criteria within a correlation window.
`CFR = failed deployments / total deployments`.

## Correlation model

Tiered, highest confidence first. The confidence level must be visible in the UI.

1. **Explicit link** — the incident references a GitHub PR, commit, release, deployment, or
   run URL. Highest confidence.
2. **Service mapping** — incident.io services mapped to repos, by manual mapping or name
   match. Medium confidence.
3. **Time window** — an incident starting within W hours of a deployment, default 24. Lowest
   confidence, **opt-in**, and disableable.

Prioritising explicit links and requiring opt-in for time-window correlation is the whole
defence against correlation noise. A CFR nobody trusts is worse than no CFR.

## Integration

OAuth connection to incident.io, with read access to incidents (timestamps, severity or
priority, affected services), and optionally incident links, custom fields, and timeline
events.

Production deployment events from [001 Deployment Ingest](001-deployment-ingest.md) are the
other half and are already in place.

## Data model

- `Incident` — workspace, incident ID, severity, timestamps, impacted services.
- `DeploymentIncidentLink` — workspace, deployment event, incident, correlation method
  (`explicit` / `service` / `time_window`), confidence score.
- `ServiceRepoMapping` — optional, workspace, service, repo.

## UX

**Settings → Integrations.** Connect incident.io, then choose the severities that count
towards CFR, enable or disable time-window correlation, set the window, and optionally map
services to repos.

**Dashboard.** A reliability section with an MTTR card (median and P75) and a CFR card with a
confidence breakdown.

**Drill-down.** For CFR, the failed deployments with their linked incidents. For MTTR, the
incidents included and their durations. Every failed deployment shows which incidents it
linked to, which correlation method was used, and the timestamps and links — the same
explainability bar the rest of the product holds.

## Acceptance criteria

- After connecting incident.io, MTTR populates for the last 90 days and CFR is
  incident-backed, not proxied.
- CFR drill-down shows deployments and incidents with the correlation method.
- Low-confidence time-window correlation can be disabled.

## Open questions

- How this interacts with workspaces: is the incident.io connection per workspace, and what
  happens when two workspaces track the same repo?
- Whether incidents are ingested via webhook, polled, or both.
- Whether reliability metrics are pre-computed or live — see the split in
  [002 Metrics Engine](002-metrics-engine.md).

## History

- **PRD 013** wrote the product requirements. No RFC was written and no code exists.
