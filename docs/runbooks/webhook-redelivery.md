# Webhook Redelivery Runbook

Use this runbook when a GitHub webhook appears to have been missed or failed
processing — for example, a deployment isn't showing up, attribution coverage
on the data quality panel has dropped, or a Sentry alert from
`app.routes.webhooks` has fired.

Distilled records every webhook delivery to the `webhook_events` table on
receipt and updates it once the dispatcher finishes. Together with GitHub's
built-in **Recent Deliveries** view, that gives us full triage and replay
capability without any custom tooling.

---

## 1. Confirm what arrived

Query `webhook_events` for the relevant time window. The table is keyed on
`delivery_id` (GitHub's `X-GitHub-Delivery` header) and tracks one of four
statuses: `received`, `succeeded`, `failed`, `no_handler`.

```sql
SELECT delivery_id, event_type, action, status, error_message, received_at, processed_at
FROM webhook_events
WHERE event_type IN ('deployment_status', 'pull_request')
  AND received_at > now() - interval '1 day'
ORDER BY received_at DESC;
```

What to look for:

- **No row** for the delivery → the webhook never reached us. Skip to step 2.
- **`status = 'received'`** more than ~10 minutes old → the dispatcher started
  but never finished. Check Sentry for a worker crash; the row will need a
  redelivery to reprocess.
- **`status = 'failed'`** → handler exception. `error_message` has the first
  exception's `Type: message` (truncated to 2 KB). Decide whether the underlying
  bug needs fixing before redelivery, or whether redelivery alone will succeed.
- **`status = 'no_handler'`** → we received the event but have no handler
  registered for that `event_type`. Either the GitHub App is subscribed to an
  event we don't process, or we're missing a handler.
- **`status = 'succeeded'`** → processing completed cleanly. Don't redeliver
  unless you have a reason to (see "When NOT to redeliver" below).

## 2. Cross-check with GitHub

Open the GitHub App settings:

1. **Settings → Developer settings → GitHub Apps → [your app] → Advanced**.
2. The **Recent Deliveries** tab shows the last 30 days of delivery attempts,
   with the response code we returned and a pasteable copy of the request +
   response payload.

Filter by event type. Match the GitHub delivery's `Guid` against
`webhook_events.delivery_id`:

- **Present in GitHub but missing from `webhook_events`** → the request never
  reached us (network, Railway outage, signature failure). The Response panel
  on GitHub's side will tell you which.
- **Present in both, status differs** → check the Response panel to see what
  GitHub thinks our HTTP response was; cross-reference with our logs.

## 3. Redeliver

If you've decided redelivery is the right action, click the **Redeliver**
button next to the delivery in GitHub. Notes:

- The redelivery is issued with a **fresh `delivery_id`**, so it appears as a
  brand-new row in `webhook_events`. This is correct — it is a new delivery
  attempt from our perspective, even though the payload is identical.
- The dispatcher is idempotent for the events we currently handle:
  `deployment_status` UPSERTs on `(tenant_id, deployment_id)` and
  `pull_request` UPSERTs on `(tenant_id, repo_id, number)`. Redelivery cannot
  produce duplicate domain rows.

## When NOT to redeliver

- The original delivery's `webhook_events.status` is already `succeeded`. The
  state we'd produce is identical; redelivery just adds noise to the table.
- The handler is currently broken and you haven't shipped a fix. Redelivery
  will just produce another `failed` row.
- The event was deliberately ignored (`no_handler`) — adding a handler is the
  right action, not redelivery.

## Bulk triage queries

Failure rate by event type over the last 7 days:

```sql
SELECT event_type,
       count(*) FILTER (WHERE status = 'succeeded')   AS succeeded,
       count(*) FILTER (WHERE status = 'failed')      AS failed,
       count(*) FILTER (WHERE status = 'no_handler')  AS no_handler,
       count(*) FILTER (WHERE status = 'received')    AS still_received
FROM webhook_events
WHERE received_at > now() - interval '7 days'
GROUP BY event_type
ORDER BY event_type;
```

Stuck deliveries (`received` longer than 10 minutes — dispatcher likely died):

```sql
SELECT delivery_id, event_type, action, received_at
FROM webhook_events
WHERE status = 'received'
  AND received_at < now() - interval '10 minutes'
ORDER BY received_at;
```

## Related

- RFC 020 — design of the retry layer + `webhook_events`.
- Sentry alert rule on logger `app.routes.webhooks` — fires on handler crashes.
