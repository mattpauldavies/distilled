import { Bar } from 'react-chartjs-2'
import type { DailyCount } from '@/types/dashboard'
import { chartTheme, formatChartDate } from '@/lib/chartTheme'

interface Props {
  dailyCounts: DailyCount[]
}

export function DeploymentChart({ dailyCounts }: Props) {
  const data = {
    labels: dailyCounts.map((d) => formatChartDate(d.date)),
    datasets: [
      {
        label: 'Deployments',
        data: dailyCounts.map((d) => d.count),
        backgroundColor: chartTheme.primary.bar,
        borderRadius: 3,
      },
    ],
  }

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { position: 'bottom' as const },
    },
    scales: {
      y: {
        beginAtZero: true,
        ticks: { precision: 0 },
        grid: { color: chartTheme.grid },
      },
      x: {
        ticks: { maxTicksLimit: 7 },
        grid: { display: false },
      },
    },
  }

  return (
    <div role="img" aria-label="Bar chart showing daily deployment counts" className="h-[220px]">
      <Bar data={data} options={options} />
    </div>
  )
}
