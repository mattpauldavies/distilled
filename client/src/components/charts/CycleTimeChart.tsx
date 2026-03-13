import { Line } from "react-chartjs-2";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
} from "chart.js";
import type { WeeklyPercentiles } from "@/types/dashboard";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend);

interface Props {
  weekly: WeeklyPercentiles[];
}

function toHours(seconds: number): number {
  return Math.round((seconds / 3600) * 10) / 10;
}

export function CycleTimeChart({ weekly }: Props) {
  const data = {
    labels: weekly.map((w) => w.week_start),
    datasets: [
      {
        label: "Median",
        data: weekly.map((w) => toHours(w.median_seconds)),
        borderColor: "#171717",
        backgroundColor: "rgba(23, 23, 23, 0.1)",
        tension: 0.3,
      },
      {
        label: "p75",
        data: weekly.map((w) => toHours(w.p75_seconds)),
        borderColor: "#737373",
        backgroundColor: "rgba(115, 115, 115, 0.1)",
        borderDash: [5, 5],
        tension: 0.3,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      y: { beginAtZero: true, title: { display: true, text: "Hours" } },
    },
  };

  return (
    <div className="h-[200px]">
      <Line data={data} options={options} />
    </div>
  );
}
