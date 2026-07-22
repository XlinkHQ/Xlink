"use client";

import type { ApexOptions } from "apexcharts";
import dynamic from "next/dynamic";
import { useTheme } from "@/lib/theme";

const ReactApexChart = dynamic(() => import("react-apexcharts"), { ssr: false });

// Shared chart palette. Primary series is the XLink accent; the secondary is a
// coherent muted indigo/slate. Danger red is only for semantic upload-vs-download.
export const CHART_COLORS = {
  accent: "#3961DB",
  slate: "#7C86A5",
  danger: "#CC3C3C",
};

// Theme-aware chart chrome: apex defaults to dark axis text + near-black grid
// lines, which vanish on our dark surface (and its light-themed tooltip renders
// as a white box on dark). Drive all of it from the active theme instead.
export function chartTheme(dark: boolean) {
  return {
    mode: (dark ? "dark" : "light") as "dark" | "light",
    axisText: dark ? "#9aa0aa" : "#6b7280",
    grid: dark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.06)",
    markerStroke: dark ? "#1a1a1c" : "#ffffff",
    tooltip: (dark ? "dark" : "light") as "dark" | "light",
  };
}

/**
 * One professional, consistent ApexOptions foundation that every area chart in
 * the console spreads from. Linear/Stripe-grade: thin smooth stroke, a single
 * faint horizontal-only gridline, muted small axis labels, light gradient wash.
 * Each chart overrides only what is genuinely chart-specific (yaxis
 * unit/formatter, series colors, tooltip y formatter, single-point markers).
 */
export function baseAreaOptions(
  dark: boolean,
  opts?: { height?: number; colors?: string[]; singlePoint?: boolean; showLegend?: boolean },
): ApexOptions {
  const t = chartTheme(dark);
  const height = opts?.height ?? 250;
  const single = opts?.singlePoint ?? false;
  return {
    chart: {
      type: "area",
      height,
      toolbar: { show: false },
      zoom: { enabled: false },
      fontFamily: "var(--warp-font)",
      foreColor: t.axisText,
      parentHeightOffset: 0,
      animations: { enabled: true, dynamicAnimation: { speed: 350 } },
    },
    theme: { mode: t.mode },
    dataLabels: { enabled: false },
    stroke: { curve: "smooth", width: 2 },
    colors: opts?.colors ?? [CHART_COLORS.accent, CHART_COLORS.slate],
    fill: {
      type: "gradient",
      gradient: { opacityFrom: 0.25, opacityTo: 0.02, stops: [0, 100] },
    },
    markers: {
      size: single ? 5 : 0,
      strokeColors: t.markerStroke,
      strokeWidth: 2,
      hover: { size: 5 },
    },
    grid: {
      borderColor: t.grid,
      strokeDashArray: 3,
      xaxis: { lines: { show: false } },
      yaxis: { lines: { show: true } },
      padding: { top: 0, right: 8, bottom: 0, left: 8 },
    },
    xaxis: {
      type: "datetime",
      axisBorder: { show: false },
      axisTicks: { show: false },
      tooltip: { enabled: false },
      labels: { datetimeUTC: false, style: { fontSize: "11px", colors: t.axisText } },
    },
    yaxis: {
      min: 0,
      tickAmount: 4,
      labels: { style: { fontSize: "11px", colors: t.axisText } },
    },
    legend: {
      show: opts?.showLegend ?? true,
      position: "top",
      horizontalAlign: "right",
      fontSize: "12px",
      labels: { colors: t.axisText },
      markers: { size: 6 },
    },
    tooltip: {
      theme: t.tooltip,
      x: { format: "MMM dd, HH:mm" },
    },
  };
}

export function MetricsAreaChart({
  cpu,
  mem,
  loading,
  height = 240,
}: {
  cpu: { x: number; y: number }[];
  mem: { x: number; y: number }[];
  loading?: boolean;
  height?: number;
}) {
  const dark = useTheme() === "dark";
  if (loading) return <div className="animate-pulse rounded-md bg-muted" style={{ height }} />;
  if (cpu.length === 0 && mem.length === 0) {
    return (
      <div className="grid place-items-center text-sm text-fg-muted" style={{ height }}>
        No metrics reported yet.
      </div>
    );
  }
  const base = baseAreaOptions(dark, {
    height,
    colors: [CHART_COLORS.accent, CHART_COLORS.slate],
    singlePoint: cpu.length === 1 && mem.length === 1,
  });
  const options: ApexOptions = {
    ...base,
    yaxis: { ...base.yaxis, max: 100, labels: { ...(base.yaxis as { labels?: object }).labels, formatter: (v) => `${Math.round(v)}%` } },
    tooltip: { ...base.tooltip, x: { format: "HH:mm" }, y: { formatter: (v) => `${v.toFixed(1)}%` } },
  };
  return (
    <div style={{ height }}>
      <ReactApexChart
        options={options}
        series={[
          { name: "CPU", data: cpu },
          { name: "Memory", data: mem },
        ]}
        type="area"
        height={height}
      />
    </div>
  );
}

export function UsageAreaChart({
  series,
  loading,
  height = 260,
  empty = "No measured traffic in the last 24h.",
}: {
  series: {
    ts?: string;
    date?: string;
    total_bytes: number;
    upload_bytes?: number;
    download_bytes?: number;
  }[];
  loading?: boolean;
  height?: number;
  empty?: string;
}) {
  const dark = useTheme() === "dark";
  if (loading) return <div className="animate-pulse rounded-md bg-muted" style={{ height }} />;

  const valid = series.filter((p) => p?.ts || p?.date);
  if (valid.length === 0) {
    return (
      <div className="grid place-items-center text-sm text-fg-muted" style={{ height }}>
        {empty}
      </div>
    );
  }

  const mb = (b: number) => +((b ?? 0) / 1024 ** 2).toFixed(2);
  const at = (p: { ts?: string; date?: string }) => new Date((p.ts ?? p.date) as string).getTime();
  const download = valid.map((p) => ({ x: at(p), y: mb(p.download_bytes ?? 0) }));
  const upload = valid.map((p) => ({ x: at(p), y: mb(p.upload_bytes ?? 0) }));

  const base = baseAreaOptions(dark, {
    height,
    // Download = accent, Upload = danger red (semantic up-vs-down).
    colors: [CHART_COLORS.accent, CHART_COLORS.danger],
    singlePoint: valid.length === 1,
  });
  const options: ApexOptions = {
    ...base,
    yaxis: {
      ...base.yaxis,
      labels: {
        ...(base.yaxis as { labels?: object }).labels,
        formatter: (v) => (v >= 1024 ? `${(v / 1024).toFixed(1)} GiB` : `${Math.round(v)} MiB`),
      },
    },
    tooltip: {
      ...base.tooltip,
      x: { format: "MMM dd, HH:mm" },
      y: { formatter: (v) => `${v >= 1024 ? (v / 1024).toFixed(2) + " GiB" : v.toFixed(1) + " MiB"}` },
    },
  };

  return (
    <div style={{ height }}>
      <ReactApexChart
        options={options}
        series={[
          { name: "Download (MiB)", data: download },
          { name: "Upload (MiB)", data: upload },
        ]}
        type="area"
        height={height}
      />
    </div>
  );
}
