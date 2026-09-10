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

`github_message` is the diagnosis, and it is the *only* place it survives:
Sentry's scrubber filters the `resp` local out of the stack trace, so an alert
alone will not tell you which of these it is.

The four we expect:

| `github_message` | Cause | Fix |
| --- | --- | --- |
| `A JSON web token could not be decoded` | GitHub found the app but could not verify our signature: the private key is not one of that app's keys — a different app's key, or one deleted in GitHub. It also covers a PEM too malformed to parse, but that fails locally before any request goes out, so on a 401 suspect the key/app pairing first. | Generate a fresh private key on the app named by `GITHUB_APP_ID`, set `GITHUB_PRIVATE_KEY`, redeploy, then delete the old key in GitHub. |
| `Integration not found` | No app matches the `iss` we sent — `GITHUB_APP_ID` is wrong (an installation id or a client id), or the app was deleted. | Correct `GITHUB_APP_ID` from the app's General settings page. |
| `'Expiration time' claim ('exp') is too far in the future` | Our clock is ahead of GitHub's. `exp` is minted at the full 10-minute maximum, so any positive skew crosses it. | Fix NTP on the app container. Measure the skew in step 2 before assuming this — do not infer it from the failure alone. |
| `'Issued at' claim ('iat') is in the future` | Our clock is behind GitHub's by more than the 60s backdate on `iat`. | Same — fix NTP. |

## 2. Ask GitHub directly

Signing a JWT locally proves only that the PEM parses. It says nothing about
whether GitHub will accept it, so go and ask. Run this on the app container —
there is no `curl` in the image, but `httpx` and `PyJWT` are runtime
dependencies and the interpreter is at `/app/.venv/bin/python`:

```bash
/app/.venv/bin/python - <<'PYEOF'
import os, time, httpx, jwt
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone

app_id = os.environ["GITHUB_APP_ID"]
pem = os.environ.get("GITHUB_PRIVATE_KEY") or open(os.environ["GITHUB_PRIVATE_KEY_PATH"]).read()
now = int(time.time())
mint = lambda iss: jwt.encode({"iat": now - 60, "exp": now + 540, "iss": str(iss)}, pem, algorithm="RS256")

with httpx.Client(base_url="https://api.github.com", timeout=30) as c:
    for label, iss in (("configured", app_id), ("bogus", 1)):
        r = c.get("/app", headers={"Authorization": f"Bearer {mint(iss)}",
                                   "Accept": "application/vnd.github+json"})
        if label == "configured":
            skew = (datetime.now(timezone.utc) - parsedate_to_datetime(r.headers["date"])).total_seconds()
            print(f"clock skew: {skew:+.1f}s (positive = we are ahead of GitHub)")
        print(f"{label} iss={iss} -> {r.status_code} {r.json().get('message')}")
PYEOF
```

`GET /app` returns the authenticating app's own record, so a 200 means the key
and `GITHUB_APP_ID` are a matched pair and the clock is acceptable to GitHub.
Keep the JWT in a variable and never print it — it is a live credential that
signs as the app.

The second request, with a deliberately bogus `iss`, is what separates the first
two rows of the table above:

- **bogus → `Integration not found` (404), configured → `could not be decoded`
  (401)** — GitHub found the app and rejected our *signature*. The key does not
  belong to that app. Re-pasting the same key will not fix it.
- **both → `could not be decoded`** — the token is rejected before the app is
  looked up, so the JWT itself is malformed. Dump its header and payload and
  check `alg`, `iss`, and that the PEM is a 2048-bit RSA key (about 27 lines,
  starting `-----BEGIN RSA PRIVATE KEY-----`).

`GITHUB_APP_ID` must be the **App ID** from the app's General settings page (a
number), not the installation id and not the client id. `GITHUB_PRIVATE_KEY`
holds the PEM with real newlines; `GITHUB_PRIVATE_KEY_PATH` is the alternative
when the key is mounted as a file. If both are set, the inline key wins.

Generating a new key in GitHub **does not** revoke the old one — delete the old
key explicitly, or a stale deployment carries on authenticating with it.

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
