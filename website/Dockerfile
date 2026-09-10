# --- build ---
FROM node:20.19.0-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# PostHog web analytics: pass the project API key at build time to enable
# the (anonymous, cookieless) analytics snippet. Omit to build without it.
ARG POSTHOG_KEY=""
ARG POSTHOG_HOST="https://d.distilledmetrics.com"
ARG POSTHOG_UI_HOST="https://eu.posthog.com"
ENV POSTHOG_KEY=$POSTHOG_KEY POSTHOG_HOST=$POSTHOG_HOST POSTHOG_UI_HOST=$POSTHOG_UI_HOST
RUN npm run build

# --- serve ---
FROM caddy:2-alpine
COPY --from=build /app/_site /srv
COPY Caddyfile /etc/caddy/Caddyfile
