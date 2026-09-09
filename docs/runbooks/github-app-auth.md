# GitHub App Auth Failures Runbook

Use this runbook when the server can't mint installation access tokens — the
symptom is a `401 Unauthorized` from
`POST https://api.github.com/app/installations/{id}/access_tokens`, usually
surfaced as a failed webhook handler or a Sentry alert from
`app.services.github_client`.

A 401 from that endpoint is **always about the app JWT**, never about the
installation. GitHub has already rejected our credentials before it looks at
which installation we asked for. (A genuinely missing installation returns 404;
a suspended one returns 403.)

---

## 1. Read the log line

Every failed mint logs the reason GitHub gave:

```
ERROR app.services.github_client: installation_token_failed installation_id=160402800 status=401 app_id=123456 github_message=...
```

`github_message` is the diagnosis. The four we expect:

| `github_message` | Cause | Fix |
| --- | --- | --- |
| `'Expiration time' claim ('exp') is too far in the future` | Our clock is ahead of GitHub's. We mint 9-minute JWTs to absorb a minute of skew, so this means skew larger than that. | Check host clock/NTP on the app container. |
| `'Issued at' claim ('iat') is in the future` | Our clock is behind GitHub's by more than the 60s backdate. | Same — fix NTP. |
| `A JSON web token could not be decoded` | `GITHUB_PRIVATE_KEY` is malformed — usually newlines mangled when the PEM was pasted into the environment. | Re-set the secret; see step 2. |
| `Integration not found` | The JWT is signed by a key that doesn't belong to `GITHUB_APP_ID` — mismatched app/key pair, or the key was revoked in GitHub. | Confirm `app_id` in the log line matches the app the key came from; regenerate if revoked. |

## 2. Verify the credentials

`GITHUB_APP_ID` must be the **App ID** from the app's settings page (a number),
not the installation id and not the client id. `GITHUB_PRIVATE_KEY` holds the
PEM with real newlines; `GITHUB_PRIVATE_KEY_PATH` is the alternative when the
key is mounted as a file. If both are set, the inline key wins.

Confirm the key parses at all:

```bash
python - <<'PY'
import os, jwt, time
key = os.environ["GITHUB_PRIVATE_KEY"]
print(jwt.encode({"iat": int(time.time()) - 60, "exp": int(time.time()) + 540,
                  "iss": os.environ["GITHUB_APP_ID"]}, key, algorithm="RS256")[:32], "...")
PY
```

A `ValueError` here means the PEM never loaded — the 401 is a secrets problem,
not a GitHub one. Rotating a key in GitHub **does not** revoke the old one until
you delete it, so generate the new key, deploy it, then delete the old one.

## 3. Repair the data the failure skipped

Token failures during `installation:created` no longer discard the
installation: repos are persisted and only **environment discovery** is
skipped, logged as

```
ERROR app.services.ingest_installation_service: environment discovery failed for org/repo installation_id=... — installation kept, environments not recorded
```

That matters because `deployment_status` events are only recorded for
environments we know are production — with no `environments` rows, deployments
are silently dropped as non-prod and delivery metrics flatline for that repo.

Once auth is fixed, re-run discovery by **redelivering the `installation`
event** from the app's Advanced tab (see
[webhook-redelivery.md](./webhook-redelivery.md)). Discovery is idempotent —
environments UPSERT on `(tenant_id, repo_id, name)`. Then redeliver any
`deployment_status` events that were skipped in the meantime.

Check which repos are missing environments:

```sql
SELECT r.full_name
FROM repositories r
LEFT JOIN environments e ON e.repo_id = r.id
WHERE r.removed_at IS NULL
GROUP BY r.full_name
HAVING count(e.id) = 0;
```

Repos legitimately have no environments (nothing configured in GitHub, or a
private repo on a Free plan, which GitHub plan-gates with a 403) — cross-check
against the repo's **Settings → Environments** page before redelivering.
