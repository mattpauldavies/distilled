const BASE_URL = "https://app.chatwoot.com"
const SDK_SRC = `${BASE_URL}/packs/js/sdk.js`
// Chatwoot website tokens are public widget identifiers, not secrets.
const WEBSITE_TOKEN = "WQZr835eubQzci26DfzXkz64"

declare global {
  interface Window {
    chatwootSDK?: { run: (config: { websiteToken: string; baseUrl: string }) => void }
  }
}

/**
 * Load the Chatwoot support widget.
 *
 * Lives in the bundle rather than as an inline script in index.html so the
 * Content-Security-Policy can keep script-src free of 'unsafe-inline'.
 */
export function initChatwoot(): void {
  if (document.querySelector(`script[src='${SDK_SRC}']`)) return

  const script = document.createElement("script")
  script.src = SDK_SRC
  script.async = true
  script.onload = () => {
    window.chatwootSDK?.run({ websiteToken: WEBSITE_TOKEN, baseUrl: BASE_URL })
  }
  document.head.appendChild(script)
}
