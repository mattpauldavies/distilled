import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { WINDOW_LABELS, isWindowAvailable } from "@/lib/daysWindow"
import type { DaysWindow } from "@/types/dashboard"

interface Props {
  window: DaysWindow
  selected: DaysWindow
  daysOfData: number
  onSelect: (window: DaysWindow) => void
}

export function DaysSelectorButton({ window, selected, daysOfData, onSelect }: Props) {
  const available = isWindowAvailable(window, daysOfData)

  const button = (
    <Button
      variant={window === selected ? "default" : "ghost"}
      size="sm"
      aria-pressed={window === selected}
      disabled={!available}
      onClick={() => onSelect(window)}
      className="rounded-none first:rounded-l-md last:rounded-r-md"
    >
      {WINDOW_LABELS[window]}
    </Button>
  )

  if (available) return <span>{button}</span>

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex cursor-not-allowed">{button}</span>
      </TooltipTrigger>
      <TooltipContent>
        Only {daysOfData} {daysOfData === 1 ? "day" : "days"} of data available
      </TooltipContent>
    </Tooltip>
  )
}
