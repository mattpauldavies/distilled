import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
} from "chart.js";
import { chartTheme } from "@/lib/chartTheme";

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  PointElement,
  LineElement,
  Tooltip,
  Legend
);

ChartJS.defaults.color = chartTheme.tick;
ChartJS.defaults.borderColor = chartTheme.grid;
ChartJS.defaults.plugins.legend.labels.color = chartTheme.legend;
ChartJS.defaults.plugins.legend.labels.boxWidth = 12;
ChartJS.defaults.plugins.legend.labels.padding = 16;
