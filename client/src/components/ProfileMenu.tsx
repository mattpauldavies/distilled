import { useClerk, useUser } from "@clerk/clerk-react"
import { Check, CircleUser } from "lucide-react"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { useTenantContext } from "@/lib/tenantContext"

interface Props {
  onOpenTeam?: () => void
}

/**
 * Top-right account chrome: avatar trigger → popover with tenant list,
 * team-management entry (owners only), and sign-out.
 *
 * Replaces the previous standalone TenantSwitcher + SignOutButton — keeps
 * the dashboard header focused on metrics controls and folds account
 * actions behind one affordance.
 */
export function ProfileMenu({ onOpenTeam }: Props) {
  const { user } = useUser()
  const { signOut } = useClerk()
  const { memberships, activeTenant, setActiveTenant } = useTenantContext()

  const displayName =
    user?.fullName || user?.username || user?.primaryEmailAddress?.emailAddress || "Signed in"
  const primaryEmail = user?.primaryEmailAddress?.emailAddress

  return (
    <Popover>
      <PopoverTrigger
        aria-label="Account menu"
        className="rounded-full ring-offset-background outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {user?.imageUrl ? (
          <img
            src={user.imageUrl}
            alt=""
            className="size-8 rounded-full border border-border object-cover"
          />
        ) : (
          <CircleUser className="size-8 text-muted-foreground" />
        )}
      </PopoverTrigger>
      <PopoverContent className="w-72 p-2">
        <div className="border-b border-border px-3 py-2">
          <p className="truncate text-sm font-medium">{displayName}</p>
          {primaryEmail && primaryEmail !== displayName ? (
            <p className="truncate text-xs text-muted-foreground">{primaryEmail}</p>
          ) : null}
        </div>

        {memberships.length > 0 ? (
          <div className="border-b border-border py-1">
            <p className="px-3 pb-1 pt-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              {memberships.length === 1 ? "Tenant" : "Switch Tenant"}
            </p>
            <ul role="menu">
              {memberships.map((m) => {
                const isActive = m.id === activeTenant?.id
                return (
                  <li key={m.id} role="none">
                    <button
                      type="button"
                      role="menuitemradio"
                      aria-checked={isActive}
                      onClick={() => setActiveTenant(m.id)}
                      className="flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-sm hover:bg-muted focus:bg-muted focus:outline-none"
                    >
                      <span className="flex min-w-0 items-center gap-2">
                        <span className="truncate">{m.name}</span>
                        <span className="shrink-0 text-[10px] uppercase tracking-wide text-muted-foreground mt-[3px]">
                          {m.role}
                        </span>
                      </span>
                      {isActive ? <Check className="size-4 shrink-0" /> : null}
                    </button>
                  </li>
                )
              })}
            </ul>
          </div>
        ) : null}

        {activeTenant?.role === "owner" && onOpenTeam ? (
          <div className="border-b border-border py-1">
            <button
              type="button"
              onClick={onOpenTeam}
              className="w-full px-3 py-1.5 text-left text-sm hover:bg-muted focus:bg-muted focus:outline-none"
            >
              Team Settings
            </button>
          </div>
        ) : null}

        <div className="py-1">
          <button
            type="button"
            onClick={() => signOut()}
            className="w-full px-3 py-1.5 text-left text-sm hover:bg-muted focus:bg-muted focus:outline-none"
          >
            Sign Out
          </button>
        </div>
      </PopoverContent>
    </Popover>
  )
}
