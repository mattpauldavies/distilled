import { Bar } from "react-chartjs-2"
import type { AgeBucket } from "@/types/dashboard"
import { chartTheme } from "@/lib/chartTheme"

interface Props {
  buckets: AgeBucket[]
}

export function PRAgeingChart({ buckets }: Props) {
  const data = {
    labels: buckets.map((b) => b.bucket),
    datasets: [
      {
        label: "PRs",
        data: buckets.map((b) => b.count),
        backgroundColor: buckets.map((_, i) => chartTheme.prAgeing[i] ?? chartTheme.prAgeing[0]),
        borderRadius: 3,
      },
    ],
  }

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
    },
    scales: {
      y: {
        beginAtZero: true,
        ticks: { precision: 0 },
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
      aria-label="Bar chart showing age distribution of open pull requests"
      className="h-[220px]"
    >
      <Bar data={data} options={options} />
    </div>
  )
}
