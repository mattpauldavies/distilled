# --- build ---
FROM node:20.19.0-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Vite inlines VITE_* at build time, so these must arrive as build args — a
# runtime environment variable would be too late and the bundle would carry
# `undefined` with no error.
ARG VITE_API_BASE_URL
ARG VITE_CLERK_PUBLISHABLE_KEY
ARG VITE_GITHUB_APP_SLUG
ARG VITE_SENTRY_DSN
ARG VITE_POSTHOG_KEY
ARG VITE_POSTHOG_HOST
RUN npm run build

# --- serve ---
FROM caddy:2-alpine
COPY --from=build /app/dist /srv
# Sourcemaps are uploaded to Sentry during the build; whatever remains must
# never reach the web root — a served .map exposes the original source.
RUN find /srv -name '*.map' -delete
COPY Caddyfile /etc/caddy/Caddyfile
