export function formatDuration(seconds: number): string {
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`
  return `${Math.round((seconds / 3600) * 10) / 10}h`
}

export function toHours(seconds: number): number {
  return Math.round((seconds / 3600) * 10) / 10
}

export function timeAgo(isoString: string | null): string {
  if (!isoString) return "never"
  const diff = Date.now() - new Date(isoString).getTime()
  if (diff < 0) return "just now"
  const minutes = Math.floor(diff / 60000)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}
