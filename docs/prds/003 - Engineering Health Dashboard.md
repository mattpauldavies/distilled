# Engineering Health Dashboard (MVP)

## 💼 Summary

A simple web-based application that automatically collects and visualises a **small set of high-impact software engineering metrics** to help Heads of Engineering at startups understand engineering health at a glance.

The product should feel like “DX but much cheaper and easier”: fast setup, minimal configuration, strong defaults, and high trust.

**MVP constraints (locked):**

- **Multi-tenant, self-serve SaaS** from day one.
- Track **exactly one GitHub repo** per tenant in MVP.
- Detect production deployments via **GitHub Environments (Option A)**.
- Default dashboard window: **last 30 days**.
- Lead time anchor: **PR merged_at → deployed_at**.
- Exclude **Change Failure Rate** and **MTTR** from MVP (see PRD 3).

---

## 🎯 Goals

- Deliver trustworthy delivery health within minutes of connecting GitHub for a single tracked repo.
- Compute and present a **small set of high-signal metrics** with clear definitions and drill-down.
- Minimise configuration: one-time repo selection, then (if needed) production environment selection.
- Maintain user trust by being explainable and avoiding speculative metrics.

## 🚫 Non-goals (MVP)

- Incidents/MTTR and Change Failure Rate.
- Team-level breakdowns (org-wide framing only; future-proof data model).
- Supporting tools beyond GitHub + GitHub Actions.
- Authentication and authorisation

---

## 👤 Target Users

### Primary persona

Head of Engineering / VP Engineering at a startup (20–250 engineers).

### Secondary persona

Engineering Ops / Platform lead who wants minimal setup and low ongoing maintenance.

---

## 🧠 Product Tenets

- **Automatic by default** after one-time setup.
- **Few metrics, high signal** (no metric sprawl).
- **Trust over guessing**: no silent fallback when production deploy detection is missing.
- **Explainability**: show underlying deploys/PRs and calculation method.
- **Privacy-first**: least privilege and minimal storage.

---

## 🔌 Integrations (MVP)

### GitHub (required)

Use a GitHub App installed on a **single selected repo** (least privilege).

Required read access:

- Repository metadata
- Pull requests & reviews
- Commits (SHAs + timestamps at minimum)
- Actions workflow runs and job results
- **Environments** (required)
- **Deployments API** (recommended; used for canonical deployment timestamps when available)

---

## 📦 Metrics Scope (MVP)

### ✅ DORA subset (MVP)

1. **Deployment Frequency**

- Definition: number of successful **production deployments** per day/week (chart uses daily buckets; summary uses last 30 days).

2. **Lead Time for Changes**

- Definition: time from **PR merged_at → deployed_at** for the first production deployment that includes the PR.
- Aggregates: median + P75.

### ✅ Flow metrics (high-signal, low controversy)

3. **PR Throughput**

- PRs merged per week.

4. **PR Cycle Time**

- PR opened_at → merged_at (median + P75).

5. **WIP proxy**

- Open PR count + PR ageing buckets (e.g. <2d, 2–7d, 7–14d, >14d).

---

## 🖥️ Core User Experience

### 🧭 Onboarding (time to value target: <10 minutes)

1. Sign up / sign in
2. “Connect GitHub”
3. GitHub App install flow:
   - Select GitHub org/user
   - **Select exactly one repo to grant access to (MVP constraint)**

4. In-app: confirm the selected repo (read-only)
5. Discover environments for the repo
6. Production environment selection:
   - If exactly one environment matches `production|prod|live` (case-insensitive) → auto-select
   - Else prompt: “Select your production environment(s)”

7. Dashboard loads (default: last **30 days**) + Data Quality panel

### 📊 Dashboard (single page MVP)

- Metric cards: Deployment frequency, Lead time, PR throughput, PR cycle time, Open PRs/WIP
- Charts:
  - Production deployments over time (daily)
  - Lead time trend (median + P75, weekly buckets)
  - PR cycle time trend (median + P75, weekly buckets)
  - Open PR ageing distribution

- Drill-down:
  - Deployments list (each with environment, timestamp source, workflow run link)
  - PR list for lead time (each with mapped deployment link + computed lead time)

- Data Quality panel (must-have)

---

## 🚢 Production Deployment Detection (Option A — Environments)

### ✅ Definitions

**Production Environment**
An environment is considered production if:

- Name matches allowlist `production|prod|live` (case-insensitive), OR
- User selects it in onboarding/settings.

**Production Deployment Event**
A production deployment event is recorded when:

- A deployment targets a selected Production Environment and is successful.

### 📌 Timestamp source (locked)

- Prefer **GitHub Deployments API timestamp** when present.
- Else use **GitHub Actions workflow run completion time**.
- Persist `timestamp_source` = `deployments_api|workflow_completion`.

### 🧾 Evidence stored (must-have, for explainability)

For each Production Deployment Event:

- tenant_id, github_org_id (if applicable), repo_id
- environment_name
- deployment_id (if Deployments API)
- workflow_id + run_id (if Actions-derived)
- commit_sha + ref
- started_at, completed_at, deployed_at
- detection_method = `environment_based`
- timestamp_source

### 🧽 De-duplication rule (MVP)

- Treat **one workflow run** as **one deployment** even if multiple jobs target prod.
- If both Deployments API and workflow evidence exist for the same commit/ref and time window, prefer Deployments API as canonical and link workflow evidence as supporting metadata.

---

## 🔗 Lead Time Attribution (PR → Deploy)

### 🎯 Lead time anchor (locked)

- Lead time per PR = `deployed_at - PR.merged_at`

### 🔍 Attribution approach

**Preferred:** associate PRs to deployments using commit SHA/ref mapping where possible.

**MVP fallback heuristic (acceptable, must be labelled):**

- Attribute PRs merged between `previous_deploy_at` and `deploy_at` to `deploy_at`.

### 🧪 Attribution quality tracking (must-have)

- % merged PRs attributed to a deployment (coverage)
- distribution of PRs per deployment (sanity signal)
- attribution method used per PR: `sha_match|time_window`

### 🔎 Explainability requirement

For each PR shown in lead time drill-down, display:

- merged_at
- deployment event used (link)
- attribution method
- computed lead time duration

---

## 🧩 Configuration (MVP minimal)

- Select one tracked repo (during GitHub install)
- Select production environment(s) (only if not auto-detected)
- Time window selector (optional UI control):
  - Default **30 days**
  - (Optional secondary quick picks: 7 / 90)

---

## 🧱 Functional Requirements (MVP)

### 🔐 Multi-tenant self-serve SaaS (hard requirement)

- Tenant isolation:
  - `tenant_id` on every row
  - enforce via application middleware + DB access patterns

- Secrets:
  - encrypted tokens at rest
  - revoke on GitHub App uninstall

- Deletion/retention:
  - tenant can request deletion; uninstall triggers token revoke and retention policy flow

### 📥 Ingestion & backfill

- Webhooks:
  - PR opened/edited/merged/closed
  - PR reviews submitted
  - workflow run completed
  - deployment events / deployment statuses (if using Deployments API)

- Backfill after install:
  - last 180 days (configurable), but UI defaults to 30 days

- Daily reconciliation to reduce webhook misses

### 🧮 Computation & versioning

- Store algorithm version per computed datapoint
- Ability to recompute after algorithm changes
- Observability:
  - ingestion lag
  - failed webhook counts
  - computation success/failure
  - deployment detection coverage

---

## 🧾 Data Quality Panel (must-have)

Display (for last 30 days):

- Tracked repo + selected production environment(s)
- Deployments detected (count)
- % deployment events with commit SHA/ref
- Lead time attribution coverage (% PRs mapped)
  Warnings + fixes:
- “No production environment configured”
- “No deployments detected to selected environment”
- “Deploy workflow doesn’t specify environment; add `environment:` to deployment job”
- “Low PR→deploy coverage; improve deployment metadata/ref linkage”

---

## ✅ Acceptance Criteria

- User can connect GitHub, install on one repo, confirm/select production environment(s), and see dashboard within 10 minutes.
- If production deployment detection fails (no envs / no env-targeted deploys):
  - DORA cards show “setup required” with explicit guidance; flow metrics still load.

- Each metric includes:
  - definition + calculation method
  - drill-down to underlying deploys/PRs

- Multi-tenancy:
  - verified isolation in tests (no cross-tenant reads).

---

## 📈 Success Metrics

- Activation:
  - % who complete repo install + production environment selection
  - median time to first dashboard

- Engagement:
  - weekly active tenants
  - repeat visits within 14 days

- Data quality:
  - % tenants with stable deployment detection
  - lead time attribution coverage distribution

---

## 🧯 Risks & Mitigations

- Repo doesn’t use GitHub Environments
  - Mitigation: crisp setup guide + in-product guidance; add alternative detection only post-MVP as explicit opt-in.

- Lead time attribution noise in complex pipelines
  - Mitigation: transparent attribution method + coverage; improve mapping iteratively.

---

## 🗺️ Future-proofing Notes (non-MVP)

- Data model stores repo-grain facts so multi-repo and team grouping can be layered without redefining metrics.
- Add team grouping later via mappings (manual tags, CODEOWNERS inference, etc.).
