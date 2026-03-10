# Reliability Metrics via incident.io

## 💼 Summary

Add **Change Failure Rate (CFR)** and **Time to Restore Service (MTTR)** by integrating with **incident.io** as the source of truth for incidents. This avoids low-trust proxies and makes the “DORA four” defensible.

This PRD also upgrades DORA Change Failure Rate from “proxy guesses” to “incident-backed correlation”.

---

## 🎯 Goals

- Provide accurate **incident-backed** CFR and MTTR.
- Correlate incidents to deployments to improve explainability and trust.
- Keep setup low-effort: connect incident.io, then either auto-correlate or configure minimal mapping.

## 🚫 Non-goals (v1)

- Creating/updating incidents from our product (read-only integration).
- Supporting multiple incident tools (PagerDuty, Opsgenie) in the same release.

---

## 👤 Target Users

- Head of Engineering / VP Eng: wants reliable reliability metrics without manual reporting.
- Eng Ops / SRE: wants correlation and audit trails.

---

## 🔌 Integration Requirements

### incident.io (required for CFR/MTTR)

- OAuth connection
- Read access to:
  - incidents (timestamps: started/declared/created, resolved/closed)
  - severity/priority
  - affected services (if configured)
  - incident links/custom fields (optional)
  - timeline events (optional)

### GitHub/GitHub Actions (already connected)

- Production Deployment Events from PRD 2/Option A remain required.

---

## ✅ Definitions

### Time to Restore Service (MTTR)

- Default: time from **incident started_at** (or declared_at if started missing) to **resolved_at** (or closed_at).
- Aggregate: median + P75 over 30/90 days.
- Allow severity filtering (default include all; configurable in settings).

### Change Failure Rate (incident-backed)

- A production deployment is considered to have “failed” if it is linked to an incident meeting criteria (e.g. Sev1/Sev2) within a correlation window.

CFR = (number of failed deployments) / (total deployments)

---

## 🔗 Correlation Model (Deployment ↔ Incident)

Use a tiered approach, prioritising high-confidence links:

1. **Explicit link** (highest confidence)

- Incident has a link/reference to:
  - GitHub PR, commit, release, deployment, or run URL

2. **Service mapping** (medium confidence)

- Map incident.io services to repos (manual mapping or name match)
- Correlate incidents affecting a service to deployments from the mapped repo(s)

3. **Time-window correlation** (lowest confidence; used only if enabled)

- If an incident starts within **W hours** after a deployment, correlate
- Default W: **24 hours** (recommend)
- Must show confidence level in UI

---

## 🧩 UX

### Settings → Integrations

- “Connect incident.io”
- Post-connect configuration (minimal, but explicit):
  - Severity levels to include in CFR (default: top 2 severities if org uses them; else user selects)
  - Enable/disable time-window correlation
  - Correlation window W (default 24h; advanced setting)
  - Optional: map services → repo(s)

### Dashboard updates

- Add reliability section:
  - MTTR card (median + P75)
  - CFR card (incident-backed) with confidence breakdown

- Drill-down:
  - for CFR: list of failed deployments with linked incidents
  - for MTTR: list of incidents included with durations

### Explainability requirements

- Every “failed deployment” shows:
  - which incident(s) it linked to
  - correlation method used (explicit / service / time window)
  - timestamps and links

---

## 🧱 Data Model Additions

- `Incident`
  - tenant_id, incident_id, severity, timestamps, impacted_services

- `DeploymentIncidentLink`
  - tenant_id, deployment_event_id, incident_id
  - correlation_method (explicit/service/time_window)
  - confidence_score

- Optional mapping tables:
  - `ServiceRepoMapping` (tenant_id, service_id, repo_id)

---

## ✅ Acceptance Criteria

- After connecting incident.io:
  - MTTR populates for last 90 days
  - CFR populates and is incident-backed (not proxy)

- CFR drill-down shows deployments ↔ incidents with correlation method.
- User can disable low-confidence correlation methods (time-window).
- Reliability metrics are clearly labelled and trusted by pilot users.

---

## 📈 Success Metrics

- % of tenants who connect incident.io after seeing “unlock reliability” messaging
- % of correlated incidents via explicit/service mapping (higher is better)
- Reduction in “unexplained CFR” complaints vs proxy approach

---

## 🧯 Risks & Mitigations

- Inconsistent incident timestamps across orgs
  - Mitigation: clear default hierarchy (started → declared → created) and disclose it

- Correlation noise
  - Mitigation: prioritise explicit links; require opt-in for time-window correlation; show confidence
