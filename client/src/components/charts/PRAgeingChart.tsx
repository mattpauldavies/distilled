import { Bar } from "react-chartjs-2";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Tooltip,
} from "chart.js";
import type { AgeBucket } from "@/types/dashboard";

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip);

const BUCKET_COLORS = [
  "hsl(142, 71%, 45%)",
  "hsl(48, 96%, 53%)",
  "hsl(25, 95%, 53%)",
  "hsl(0, 84%, 60%)",
];

interface Props {
  buckets: AgeBucket[];
}

export function PRAgeingChart({ buckets }: Props) {
  const data = {
    labels: buckets.map((b) => b.bucket),
    datasets: [
      {
        label: "PRs",
        data: buckets.map((b) => b.count),
        backgroundColor: buckets.map((_, i) => BUCKET_COLORS[i] ?? BUCKET_COLORS[0]),
        borderRadius: 4,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      y: { beginAtZero: true, ticks: { precision: 0 } },
    },
  };

  return (
    <div className="h-[200px]">
      <Bar data={data} options={options} />
    </div>
  );
}
