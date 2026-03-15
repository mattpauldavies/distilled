/**
 * Central chart colour definitions.
 * All chart components and chartSetup.ts import from here.
 * Update this file when the design system palette changes.
 */
export const chartTheme = {
  primary: {
    bar: "rgba(212, 168, 83, 0.8)",
    line: "#d4a853",
    fill: "rgba(212, 168, 83, 0.08)",
    point: "#d4a853",
  },
  secondary: {
    line: "rgba(240, 240, 244, 0.35)",
    fill: "transparent",
    point: "rgba(240, 240, 244, 0.35)",
  },
  grid: "rgba(240, 240, 244, 0.07)",
  tick: "#8e8ea0",
  legend: "#9a9aaa",
  prAgeing: [
    "rgba(52, 211, 153, 0.85)",
    "rgba(251, 191, 36, 0.85)",
    "rgba(251, 146, 60, 0.85)",
    "rgba(248, 113, 113, 0.85)",
  ],
} as const;
