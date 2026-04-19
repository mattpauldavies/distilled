import { useClerk } from "@clerk/clerk-react"
import { Button } from "@/components/ui/button"

export function SignOutButton() {
  const { signOut } = useClerk()
  return (
    <Button variant="outline" size="sm" onClick={() => signOut()}>
      Sign out
    </Button>
  )
}
