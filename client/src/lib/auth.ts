import { useAuth } from "@clerk/clerk-react"

const HAS_CLERK = !!import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

// When Clerk is configured, delegate to useAuth().getToken.
function useGetTokenClerk(): () => Promise<string | null> {
  // eslint-disable-next-line react-hooks/rules-of-hooks
  const { getToken } = useAuth()
  return getToken
}

// When Clerk is not configured (dev / smoke tests), always return null.
function useGetTokenNoop(): () => Promise<string | null> {
  return () => Promise.resolve(null)
}

/**
 * Returns a stable getToken function.
 * - Clerk configured: returns Clerk's getToken (attaches JWT to every request).
 * - Clerk absent: returns a no-op (server dev-bypass mode handles auth instead).
 *
 * The export is a module-level constant so React's rules of hooks are satisfied —
 * the same underlying function is called on every render.
 */
export const useGetToken: () => () => Promise<string | null> = HAS_CLERK
  ? useGetTokenClerk
  : useGetTokenNoop
