"use client";

import type { ApexOptions } from "apexcharts";
import dynamic from "next/dynamic";

const ReactApexChart = dynamic(() => import("react-apexcharts"), { ssr: false });

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
  const download = valid.map((p) => ({ x: at(p), y: mb(p.download_bytes ?? p.total_bytes) }));
  const upload = valid.map((p) => ({ x: at(p), y: mb(p.upload_bytes ?? 0) }));

  const options: ApexOptions = {
    chart: {
      type: "area",
      height,
      sparkline: { enabled: true },
      fontFamily: "var(--warp-font)",
    },
    dataLabels: { enabled: false },
    stroke: { curve: "smooth", width: 4 },
    colors: ["#008ffb", "#5564be"],
    markers: { size: valid.length === 1 ? 5 : 0, strokeColors: "#ffffff", strokeWidth: 2, hover: { size: 6 } },
    fill: {
      type: "gradient",
      gradient: { shadeIntensity: 1, opacityFrom: 0.65, opacityTo: 0.5, stops: [0, 100] },
    },
    yaxis: { min: 0 },
    xaxis: { type: "datetime" },
    tooltip: {
      theme: "light",
      x: { format: "MMM dd, HH:mm" },
      y: { formatter: (v) => `${v >= 1024 ? (v / 1024).toFixed(2) + " GB" : v.toFixed(1) + " MB"}` },
    },
  };

  return (
    <div style={{ height, overflow: "hidden" }}>
      <ReactApexChart
        options={options}
        series={[
          { name: "Download (MB)", data: download },
          { name: "Upload (MB)", data: upload },
        ]}
        type="area"
        height={height}
      />
    </div>
  );
}
