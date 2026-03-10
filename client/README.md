# Client

React 19 frontend built with Vite, TypeScript, and Tailwind CSS. Pre-configured for shadcn/ui.

## Setup

```sh
nvm use        # uses .nvmrc (Node 20)
npm install
```

## Run

```sh
npm run dev    # http://localhost:5173
```

Vite proxies `/api` requests to `http://localhost:8000` so the backend must be running.

## Build

```sh
npm run build  # outputs to dist/
```

## Adding shadcn/ui components

`components.json` is already configured. Add components with:

```sh
npx shadcn@latest add button
npx shadcn@latest add card
```

## Structure

```
src/
  main.tsx            # Entry point
  App.tsx             # Main page — item form + list
  index.css           # Tailwind + theme vars
  lib/utils.ts        # cn() helper for shadcn
  components/ui/      # shadcn components (added via CLI)
```
