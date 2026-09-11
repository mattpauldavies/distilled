import { beforeEach, describe, expect, it } from "vitest"
import { initChatwoot } from "./chatwoot"

describe("initChatwoot", () => {
  beforeEach(() => {
    document.head.innerHTML = ""
    document.body.innerHTML = "<div id='root'></div>"
    delete (window as { chatwootSDK?: unknown }).chatwootSDK
  })

  it("injects the Chatwoot SDK script from app.chatwoot.com", () => {
    initChatwoot()

    const script = document.querySelector<HTMLScriptElement>(
      "script[src='https://app.chatwoot.com/packs/js/sdk.js']"
    )
    expect(script).not.toBeNull()
    expect(script?.async).toBe(true)
  })

  it("runs the SDK with the site token once the script loads", () => {
    let runArgs: unknown = null
    ;(window as { chatwootSDK?: unknown }).chatwootSDK = {
      run: (args: unknown) => {
        runArgs = args
      },
    }

    initChatwoot()
    const script = document.querySelector<HTMLScriptElement>(
      "script[src='https://app.chatwoot.com/packs/js/sdk.js']"
    )
    script?.onload?.(new Event("load"))

    expect(runArgs).toEqual({
      websiteToken: "WQZr835eubQzci26DfzXkz64",
      baseUrl: "https://app.chatwoot.com",
    })
  })

  it("does not inject twice", () => {
    initChatwoot()
    initChatwoot()

    expect(
      document.querySelectorAll("script[src='https://app.chatwoot.com/packs/js/sdk.js']")
    ).toHaveLength(1)
  })
})
