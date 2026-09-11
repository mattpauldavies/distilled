// Serving-layer tests: they boot the real Caddyfile over the built _site so
// that the site's URL contract (see docs/adrs/006-website-url-canonicalisation.md)
// is verified against the server that actually serves it in production.
//
// Requires the `caddy` binary on PATH (or CADDY_BIN pointing at it) and a
// built _site — `npm test` runs the build first.
import { spawn } from "node:child_process";
import { createServer } from "node:net";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";
import test, { after, before } from "node:test";

const websiteDir = dirname(dirname(fileURLToPath(import.meta.url)));
const siteRoot = join(websiteDir, "_site");
const caddyBin = process.env.CADDY_BIN || "caddy";

let caddy;
let origin;
let spawnError;

function freePort() {
  return new Promise((resolve, reject) => {
    const server = createServer();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      server.close(() => resolve(port));
    });
  });
}

async function waitForReady(url, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (spawnError) {
      throw new Error(
        `Could not run "${caddyBin}" (${spawnError.code}). Install Caddy, or set ` +
          `CADDY_BIN to its path — the routing tests exercise the real Caddyfile.`
      );
    }
    try {
      await fetch(url, { redirect: "manual" });
      return;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
  }
  throw new Error(`Caddy did not start listening on ${url} within ${timeoutMs}ms`);
}

const get = (path) => fetch(`${origin}${path}`, { redirect: "manual" });

before(async () => {
  assert.ok(
    existsSync(join(siteRoot, "terms.html")),
    "_site is not built — run `npm run build` in website/ first"
  );

  const port = await freePort();
  origin = `http://127.0.0.1:${port}`;

  caddy = spawn(
    caddyBin,
    ["run", "--config", join(websiteDir, "Caddyfile"), "--adapter", "caddyfile"],
    { env: { ...process.env, PORT: String(port), SITE_ROOT: siteRoot }, stdio: "ignore" }
  );
  caddy.on("error", (err) => {
    spawnError = err;
  });

  await waitForReady(origin);
});

after(() => caddy?.kill());

test("extensionless page URLs serve the page", async () => {
  for (const [path, title] of [
    ["/terms", "Website Terms of Use — Distilled"],
    ["/privacy", "Privacy Policy — Distilled"],
    ["/app-terms", "Application Terms and Conditions — Distilled"],
    ["/getting-started", "Getting Started — Distilled"],
  ]) {
    const response = await get(path);
    assert.equal(response.status, 200, `${path} should serve the page`);
    assert.match(await response.text(), new RegExp(`<title>${title}</title>`));
  }
});

test("the homepage serves at the site root", async () => {
  const response = await get("/");
  assert.equal(response.status, 200);
  assert.match(await response.text(), /Engineering intelligence/);
});

test(".html URLs redirect permanently to their canonical extensionless form", async () => {
  for (const path of ["/terms", "/privacy", "/app-terms", "/getting-started"]) {
    const response = await get(`${path}.html`);
    assert.equal(response.status, 301, `${path}.html should redirect`);
    assert.equal(response.headers.get("location"), path);
  }
});

test("redirects keep the query string, so campaign tags survive", async () => {
  const response = await get("/terms.html?utm_source=newsletter&utm_medium=email");
  assert.equal(response.status, 301);
  assert.equal(
    response.headers.get("location"),
    "/terms?utm_source=newsletter&utm_medium=email"
  );
});

test("the homepage's aliases redirect to the site root", async () => {
  for (const path of ["/index.html", "/index"]) {
    const response = await get(path);
    assert.equal(response.status, 301, `${path} should redirect`);
    assert.equal(response.headers.get("location"), "/");
  }
});

test("static assets are served untouched", async () => {
  const response = await get("/images/distilled-screenshot.png");
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("content-type"), "image/png");
});

test("a missing page 404s rather than falling back to the homepage", async () => {
  const response = await get("/no-such-page");
  assert.equal(response.status, 404);
  assert.doesNotMatch(await response.text(), /Engineering intelligence/);
});

test("backslash paths cannot mint off-site redirects", async () => {
  // Browsers treat \ as / when resolving a Location header, so a 301 to
  // "/\evil.com/x" leaves the site as "https://evil.com/x". Backslash paths
  // must fall through to a 404, never a redirect.
  for (const path of [
    "/%5Cevil.com/x.html",
    "/%5Cevil.com/x.html?utm_source=phish",
    "/foo%5Cevil.com/x.html",
  ]) {
    const response = await get(path);
    const location = response.headers.get("location") ?? "";
    assert.ok(
      !location.includes("\\"),
      `${path} must not redirect to a backslash path (got ${location})`
    );
    assert.equal(response.status, 404, `${path} should 404`);
  }
});
