import { Bar } from "react-chartjs-2";
import type { AgeBucket } from "@/types/dashboard";

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
    plugins: {
      legend: { position: "bottom" as const },
    },
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
