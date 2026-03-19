import { Line } from "react-chartjs-2"
import type { WeeklyPercentiles } from "@/types/dashboard"
import { chartTheme, formatChartDate } from "@/lib/chartTheme"

interface Props {
  weekly: WeeklyPercentiles[]
}

function toHours(seconds: number): number {
  return Math.round((seconds / 3600) * 10) / 10
}

export function CycleTimeChart({ weekly }: Props) {
  const data = {
    labels: weekly.map((w) => formatChartDate(w.week_start)),
    datasets: [
      {
        label: "Median",
        data: weekly.map((w) => toHours(w.median_seconds)),
        borderColor: chartTheme.primary.line,
        backgroundColor: chartTheme.primary.fill,
        tension: 0.3,
        borderWidth: 2,
        pointRadius: 3,
        pointBackgroundColor: chartTheme.primary.point,
      },
      {
        label: "P75",
        data: weekly.map((w) => toHours(w.p75_seconds)),
        borderColor: chartTheme.secondary.line,
        backgroundColor: chartTheme.secondary.fill,
        borderDash: [5, 5],
        tension: 0.3,
        borderWidth: 1.5,
        pointRadius: 2,
        pointBackgroundColor: chartTheme.secondary.point,
      },
    ],
  }

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { position: "bottom" as const },
    },
    scales: {
      y: {
        beginAtZero: true,
        title: { display: true, text: "Hours" },
        grid: { color: chartTheme.grid },
      },
      x: {
        grid: { display: false },
      },
    },
  }

  return (
    <div
      role="img"
      aria-label="Line chart showing weekly PR cycle time: median and 75th percentile in hours"
      className="h-[220px]"
    >
      <Line data={data} options={options} />
    </div>
  )
}
