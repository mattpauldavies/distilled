import { useAuth } from "@clerk/clerk-react"

export function useGetToken(): () => Promise<string | null> {
  const { getToken } = useAuth()
  return getToken
}
