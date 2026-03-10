# Deployment Detection

## 💼 Summary

A robust, explainable backend system for detecting **production deployments via GitHub Environments** and linking changes (PRs) to those deployments. This is the foundation for accurate DORA metrics and user trust.

---

## 🎯 Goals

- Detect production deployments with **high confidence** using Environments.
- Link PRs → production deployments with measurable coverage.

## 🚫 Non-goals (MVP)

- Incidents/MTTR and Change Failure Rate.

---

## ✅ Definitions

### Production Environment

An environment is “Production” if:

- name matches allowlist (`production|prod|live`, case-insensitive), OR
- user selects it during onboarding.

### Production Deployment Event

Recorded when:

- A GitHub Actions workflow run completes successfully AND references a selected production environment.
- De-duplication rule: one deployment event per workflow run (even if multiple jobs target prod).

---

## 🔍 Detection & Storage Requirements

### 📌 Inputs

- Environments list per repo
- Workflow run + job metadata (must include environment references)
- Commit SHA/ref for run

### 🧭 Detection Steps (MVP)

1. Discover environments across selected repos
2. Identify production candidates by allowlist
3. If ambiguous, require user selection (single onboarding step)
4. Ingest successful workflow runs that reference selected production environments
5. De-duplicate and persist as Production Deployment Events

### 🗃️ Evidence stored (must-have)

For each Production Deployment Event:

- tenant_id, org_id, repo_id
- environment_name
- workflow_id + run_id
- commit_sha + ref
- started_at, completed_at (deployed_at = completed_at default)
- detection_method = `environment_based`

---

## 🔗 PR → Deployment Attribution (Lead Time)

### Preferred method

- Use commit SHA ancestry / association where available (repo API dependent).

### MVP heuristic (acceptable)

- Attribute PRs merged between previous_deploy_at and deploy_at to deploy_at.
### Explainability

- For any PR’s lead time, show:
  - PR merged_at
  - deployment event used (link)
  - attribution method used (sha-match vs time-window)

---

## ✅ Acceptance Criteria

- In repos using Environments for prod deploys, detection reliably identifies production deployments.
- User can resolve ambiguous environment selection in one step.
- PRs are attributed to deployments via time-window heuristic.

---

## 🧯 Risks & Mitigations

- **No Environments usage**
  - Mitigation: explicit “setup required” gating; provide recommended patterns to adopt Environments.

- **Partial adoption**
  - Mitigation: repo-level warnings; roadmap per-repo environment overrides.
