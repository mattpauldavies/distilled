# --- build ---
FROM node:20.19.0-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# --- serve ---
FROM caddy:2-alpine
COPY --from=build /app/_site /srv
COPY Caddyfile /etc/caddy/Caddyfile
