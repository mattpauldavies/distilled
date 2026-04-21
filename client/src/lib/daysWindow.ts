import type { DaysWindow } from "@/types/dashboard"

export const WINDOWS: DaysWindow[] = [30, 90, 180]

export const WINDOW_LABELS: Record<DaysWindow, string> = {
  30: "30d",
  90: "90d",
  180: "6m",
}

export function isWindowAvailable(window: DaysWindow, daysOfData: number | null): boolean {
  if (daysOfData == null) return true
  const index = WINDOWS.indexOf(window)
  if (index <= 0) return true
  const previousWindow = WINDOWS[index - 1]
  return daysOfData > previousWindow
}
