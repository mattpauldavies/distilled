import { Bar } from "react-chartjs-2";
import type { DailyCount } from "@/types/dashboard";

interface Props {
  dailyCounts: DailyCount[];
}

export function DeploymentChart({ dailyCounts }: Props) {
  const data = {
    labels: dailyCounts.map((d) => d.date),
    datasets: [
      {
        label: "Deployments",
        data: dailyCounts.map((d) => d.count),
        backgroundColor: "rgba(23, 23, 23, 0.7)",
        borderRadius: 4,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      y: { beginAtZero: true, ticks: { precision: 0 } },
      x: { ticks: { maxTicksLimit: 7 } },
    },
  };

  return (
    <div className="h-[200px]">
      <Bar data={data} options={options} />
    </div>
  );
}
