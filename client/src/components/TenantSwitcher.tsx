import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { useTenantContext } from "@/lib/tenantContext"

export function TenantSwitcher() {
  const { memberships, activeTenant, setActiveTenant } = useTenantContext()

  if (memberships.length === 0 || !activeTenant) return null

  // Single membership: render a static label, no chrome.
  if (memberships.length === 1) {
    return (
      <span className="text-xs font-medium text-muted-foreground" aria-label="Active tenant">
        {activeTenant.name}
      </span>
    )
  }

  return (
    <Select value={activeTenant.id} onValueChange={(value) => setActiveTenant(value)}>
      <SelectTrigger size="sm" className="min-w-[10rem]" aria-label="Switch tenant">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {memberships.map((m) => (
          <SelectItem key={m.id} value={m.id}>
            <span className="flex items-center gap-2">
              <span>{m.name}</span>
              <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                {m.role}
              </span>
            </span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
