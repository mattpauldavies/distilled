# Local Testing Runbook

End-to-end guide for running and testing Distilled locally, including GitHub App integration.

## Prerequisites

- Python 3.12+ with [Poetry](https://python-poetry.org/)
- Node 20+ (via [nvm](https://github.com/nvm-sh/nvm))
- [Docker](https://docs.docker.com/get-docker/)
- Make
- A GitHub account (for GitHub App setup)
- [smee.io](https://smee.io/) or [ngrok](https://ngrok.com/) (for webhook forwarding)

---

## 1. Start the Database

```sh
make db-up        # starts Postgres 16 via Docker on port 5432
make migrate      # applies Alembic migrations
```

Verify it's running:

```sh
docker compose ps   # should show postgres healthy
```

To reset to a clean slate:

```sh
make db-reset     # drops volume, restarts Postgres
make migrate      # re-apply migrations
```

---

## 2. Create a GitHub App

Go to **GitHub Settings > Developer settings > GitHub Apps > New GitHub App**.

### App settings

| Field          | Value                                |
| -------------- | ------------------------------------ |
| App name       | `distilled-dev` (or anything unique) |
| Homepage URL   | `http://localhost:8000`              |
| Webhook URL    | Your smee/ngrok URL (see step 3)     |
| Webhook secret | Generate one: `openssl rand -hex 20` |

Note: the webhook secret is used to authenticate the webhook, it is separate from the app client secret key.

### Permissions

| Permission    | Access                   |
| ------------- | ------------------------ |
| Deployments   | Read-only                |
| Pull requests | Read-only                |
| Metadata      | Read-only (auto-granted) |
| Environments  | Read-only                |

### Events to subscribe to

- [x] Deployment status
- [x] Pull request
- [x] Installation

### Post-creation

1. Note the **App ID** (shown at top of app settings page)
2. Generate a **private key** — downloads a `.pem` file
3. Move the `.pem` somewhere safe, e.g. `server/github-app.pem`
4. Install the app on your GitHub account/org (select specific repos to test with)

---

## 3. Set Up Webhook Forwarding

GitHub needs to reach your local machine. Two options:

### Option A: smee.io (recommended, no signup)

```sh
# install smee client
npm install -g smee-client

# create a channel at https://smee.io — copy the URL

# forward webhooks to your local server
smee -u https://smee.io/YOUR_CHANNEL_ID -t http://localhost:8000/api/webhooks/github
```

### Option B: ngrok

```sh
ngrok http 8000
# copy the https://xxxx.ngrok.io URL
# set it as your GitHub App webhook URL: https://xxxx.ngrok.io/api/webhooks/github
```

Keep the forwarding process running in a separate terminal.

---

## 4. Configure Environment Variables

```sh
cd server
cp .env.example .env
```

Edit `.env`:

```env
DATABASE_URL=postgresql+asyncpg://distilled:distilled@localhost:5432/distilled
GITHUB_APP_ID=123456                    # your App ID from step 2
GITHUB_PRIVATE_KEY_PATH=github-app.pem  # path to your .pem file
GITHUB_WEBHOOK_SECRET=your_secret_here  # the webhook secret from step 2
SEED_TENANT_ID=00000000-0000-0000-0000-000000000001
SEED_TENANT_NAME=dev
```

---

## 5. Start the Server

```sh
make dev          # starts both server (8000) and client (5173)
# or just the server:
make dev-server
```

Verify:

```sh
curl http://localhost:8000/api/health
# {"status":"ok"}
```

API docs available at http://localhost:8000/docs

---

## 6. Install the GitHub App

1. Go to your GitHub App settings page
2. Click **Install App** in the sidebar
3. Choose your account/org and select the repos you want to test with
4. Click **Install**

This triggers an `installation` webhook. Check your server logs — you should see:

```
webhook received event_type=installation action=created
```

Verify the data landed:

```sh
curl http://localhost:8000/api/repos | python3 -m json.tool
```

You should see your installed repos listed.

---

## 7. Test Deployment Detection

### Trigger a test deployment

The easiest way is to have a GitHub Actions workflow that deploys to a GitHub Environment. Minimal example workflow (`.github/workflows/deploy.yml` in your test repo):

```yaml
name: Deploy
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production
    steps:
      - run: echo "Deployed!"
```

Push a commit to `main` on your test repo. This will:

1. Run the workflow targeting the `production` environment
2. GitHub sends a `deployment_status` webhook with `state: success`
3. Distilled detects the production environment and creates a deployment event

### Verify

```sh
# check deployments
curl http://localhost:8000/api/deployments | python3 -m json.tool

# check a specific deployment's attributed PRs
curl http://localhost:8000/api/deployments/{id} | python3 -m json.tool
```

---

## 8. Test PR Attribution

1. Create a branch on your test repo
2. Open a PR targeting `main`
3. Merge the PR — triggers a `pull_request` webhook (action: closed, merged: true)
4. Push another commit to `main` to trigger a deployment
5. The deployment should attribute your merged PR

### Verify

```sh
# list PRs
curl http://localhost:8000/api/pull-requests | python3 -m json.tool

# check specific PR and its linked deployment
curl http://localhost:8000/api/pull-requests/{id} | python3 -m json.tool
```

---

## 9. Test Environment Configuration

By default, environments matching `production|prod|live` (case-insensitive) are auto-detected as production.

To manually toggle an environment:

```sh
# list environments (optionally filter by repo_id)
curl http://localhost:8000/api/environments?repo_id={repo_id} | python3 -m json.tool

# toggle is_production
curl -X PATCH http://localhost:8000/api/environments/{env_id} \
  -H "Content-Type: application/json" \
  -d '{"is_production": true}'
```

---

## Troubleshooting

### Webhooks not arriving

- Verify smee/ngrok is running and pointing to `http://localhost:8000/api/webhooks/github`
- Check GitHub App > Advanced > Recent Deliveries for delivery status
- Check the webhook secret matches between GitHub and your `.env`

### 401 on webhook endpoint

- Webhook signature verification failed
- Ensure `GITHUB_WEBHOOK_SECRET` in `.env` matches exactly what you set in GitHub App settings

### No repos after installation

- Check server logs for errors during installation handler
- Verify `GITHUB_APP_ID` and `GITHUB_PRIVATE_KEY_PATH` are correct
- Ensure the private key file is readable and is the correct `.pem` for your app

### Deployments not detected

- Confirm the repo has a GitHub Environment named `production` (or matching `prod|live`)
- Check that `is_production` is `true` for the environment: `GET /api/environments?repo_id={id}`
- Verify the GitHub Actions workflow targets the environment with `environment: production`

### Database issues

```sh
make db-reset     # nuclear option: drops everything
make migrate      # re-apply migrations
```

### Port conflicts

- Postgres: 5432 (change in `docker-compose.yml`)
- Server: 8000 (change in Makefile `dev-server` target)
- Client: 5173 (change in `client/vite.config.ts`)
