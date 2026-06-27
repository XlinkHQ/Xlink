"use client";

import { useQuery } from "@tanstack/react-query";
import type { ApexOptions } from "apexcharts";
import { ArrowUpDown, Podcast } from "lucide-react";
import dynamic from "next/dynamic";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { ApiError, listNodes, type NodeRead, restartPanel, systemStats, trafficSummary } from "@/lib/api";
import { toast } from "@/components/ui/toast";
import { useTheme } from "@/lib/theme";
import { isNodeOnline, relativeTime } from "./nodes/util";

const OS_LOGOS: Record<string, string> = {
  ubuntu: "/warp/os/ubuntu.png",
  debian: "/warp/os/debian.png",
};
function osLogo(slug?: string): string | null {
  return OS_LOGOS[(slug ?? "").toLowerCase()] ?? null;
}

const ReactApexChart = dynamic(() => import("react-apexcharts"), { ssr: false });

function gb(v: number): string {
  return (v / 1024 ** 3).toFixed(1);
}
function fmtUptime(s: number): string {
  if (s <= 0) return "—";
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function Card({
  dot,
  title,
  action,
  children,
}: {
  dot: string;
  title: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  const [collapsed, setCollapsed] = useState(false);
  return (
    <div className={`warp-card ${collapsed ? "warp-card-collapsed" : ""}`}>
      <div className="warp-card-header">
        <div>
          <span className={`warp-card-dot ${dot}`} />
          <h4>{title}</h4>
        </div>
        <div className="warp-card-head-right">
          {action}
          <button
            type="button"
            className="warp-card-toggle"
            aria-label={collapsed ? "Expand" : "Collapse"}
            onClick={() => setCollapsed((c) => !c)}
          >
            <ArrowUpDown size={13} />
          </button>
        </div>
      </div>
      <div className="warp-card-body">{children}</div>
    </div>
  );
}

function FootRow({ k, v }: { k: string; v: string }) {
  return (
    <p>
      <span className="warp-foot-k">
        <i className="warp-foot-dot" />
        {k}:
      </span>
      <span className="warp-v">{v}</span>
    </p>
  );
}

function RadialCard({
  dot,
  title,
  status,
  pct,
  rows,
}: {
  dot: string;
  title: string;
  status: string;
  pct: number;
  rows: Array<[string, string]>;
}) {
  return (
    <Card dot={dot} title={title} action={<span className="warp-card-status">{status}</span>}>
      <div className="warp-radial-pct">{pct}%</div>
      <div className="warp-radial-bar">
        <div className="warp-radial-fill" style={{ width: `${Math.min(100, pct)}%` }} />
      </div>
      <div className="warp-card-footer">
        {rows.map(([k, v]) => (
          <FootRow key={k} k={k} v={v} />
        ))}
      </div>
    </Card>
  );
}

export function DashboardScreen() {
  const theme = useTheme();
  const q = useQuery({ queryKey: ["system"], queryFn: () => systemStats(), refetchInterval: 3000 });
  const nodesQ = useQuery({ queryKey: ["nodes"], queryFn: () => listNodes(), refetchInterval: 10000 });
  const trafficQ = useQuery({ queryKey: ["traffic"], queryFn: () => trafficSummary(), refetchInterval: 5000 });

  const s = q.data;
  const nodes = (nodesQ.data?.items ?? []) as NodeRead[];
  const t = trafficQ.data;

  const ramPct = s && s.ram_total_bytes > 0 ? Math.round((s.ram_used_bytes / s.ram_total_bytes) * 100) : 0;
  const diskPct = s && s.disk_total_bytes > 0 ? Math.round((s.disk_used_bytes / s.disk_total_bytes) * 100) : 0;
  const cpuPct = Math.round(s?.cpu_percent ?? 0);

  const [down, setDown] = useState<{ x: number; y: number }[]>([]);
  const [up, setUp] = useState<{ x: number; y: number }[]>([]);
  const prevTotals = useRef<{ d: number; u: number; at: number } | null>(null);
  useEffect(() => {
    if (!t) return;
    const now = trafficQ.dataUpdatedAt || Date.now();
    const dBytes = t.download_bytes;
    const uBytes = t.upload_bytes;
    const prev = prevTotals.current;
    if (prev) {
      const dt = Math.max(1, (now - prev.at) / 1000);
      const dMbps = +((Math.max(0, dBytes - prev.d) * 8) / 1e6 / dt).toFixed(2);
      const uMbps = +((Math.max(0, uBytes - prev.u) * 8) / 1e6 / dt).toFixed(2);
      setDown((s) => [...s.slice(-59), { x: now, y: dMbps }]);
      setUp((s) => [...s.slice(-59), { x: now, y: uMbps }]);
    } else {
      setDown([{ x: now, y: 0 }]);
      setUp([{ x: now, y: 0 }]);
    }
    prevTotals.current = { d: dBytes, u: uBytes, at: now };
  }, [trafficQ.dataUpdatedAt]);

  const activity = [...nodes]
    .filter((n) => n.last_seen_at)
    .sort((a, b) => Date.parse(b.last_seen_at ?? "") - Date.parse(a.last_seen_at ?? ""))
    .slice(0, 8);

  const onRestart = async () => {
    try {
      await restartPanel();
      toast("success", "Panel is restarting…");
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Restart failed.");
    }
  };

  const fmtRate = (v: number) => (v >= 1000 ? `${(v / 1000).toFixed(2)} Gbps` : `${v.toFixed(1)} Mbps`);
  const chartOptions: ApexOptions = {
    chart: {
      id: "net-throughput",
      type: "area",
      height: 176,
      toolbar: { show: false },
      animations: { enabled: true, dynamicAnimation: { speed: 350 } },
      fontFamily: "var(--warp-font)",
    },
    dataLabels: { enabled: false },
    stroke: { curve: "smooth", width: 2.5 },
    fill: {
      type: "gradient",
      gradient: { shadeIntensity: 1, opacityFrom: 0.45, opacityTo: 0.05, stops: [0, 100] },
    },
    colors: ["#008ffb", "#5564be"],
    markers: { size: 0, hover: { size: 5 } },
    grid: { borderColor: "rgba(128,128,128,0.15)", strokeDashArray: 4 },
    legend: { show: true, position: "top", horizontalAlign: "right" },
    xaxis: {
      type: "datetime",
      labels: { datetimeUTC: false, format: "HH:mm:ss", style: { fontSize: "11px" } },
    },
    yaxis: {
      min: 0,
      forceNiceScale: true,
      labels: { formatter: (v) => fmtRate(v), style: { fontSize: "11px" } },
    },
    tooltip: {
      theme: "light",
      x: { format: "HH:mm:ss" },
      y: { formatter: (v) => fmtRate(v) },
    },
  };
  const chartSeries = [
    { name: "Download", data: down },
    { name: "Upload", data: up },
  ];

  return (
    <div className="warp-panel">
      <Card
        dot="span-blue"
        title="Network Traffic"
        action={
          <span className="warp-traffic-legend">
            <span><i className="warp-legend-down" /> Download {gb(t?.download_bytes ?? 0)} GB</span>
            <span><i className="warp-legend-up" /> Upload {gb(t?.upload_bytes ?? 0)} GB</span>
          </span>
        }
      >
        {down.length > 0 ? (
          <ReactApexChart options={chartOptions} series={chartSeries} type="area" height={176} />
        ) : (
          <div className="warp-chart-empty">Collecting traffic…</div>
        )}
      </Card>

      <div className="warp-grid-3">
        <RadialCard
          dot="span-green"
          title="CPU"
          status={s ? "Running" : "…"}
          pct={cpuPct}
          rows={[["Cores", `${s?.cpu_cores ?? 0}`], ["Processes", `${s?.process_count ?? 0}`], ["Load", `${(s?.load_avg_1 ?? 0).toFixed(2)}`]]}
        />
        <RadialCard
          dot="span-blue"
          title="RAM"
          status={s ? "Running" : "…"}
          pct={ramPct}
          rows={[["Used", `${gb(s?.ram_used_bytes ?? 0)} GB`], ["Total", `${gb(s?.ram_total_bytes ?? 0)} GB`], ["Free", `${gb((s?.ram_total_bytes ?? 0) - (s?.ram_used_bytes ?? 0))} GB`]]}
        />
        <RadialCard
          dot="span-orange"
          title="Disk"
          status={s ? "Running" : "…"}
          pct={diskPct}
          rows={[["Used", `${gb(s?.disk_used_bytes ?? 0)} GB`], ["Total", `${gb(s?.disk_total_bytes ?? 0)} GB`], ["Swap", `${gb(s?.swap_used_bytes ?? 0)} GB`]]}
        />
      </div>

      <div className="warp-grid-2">
        <Card dot="span-pink" title="System Info">
          <div className="warp-si-grid">
            <div className="warp-si-box">
              <Podcast className="warp-si-iconchip" size={13} aria-hidden />
              <span className="warp-si-ip">
                <h4>{s?.ip_address || "—"}</h4>
                <p>{s?.ip6_address || s?.mac_address || "—"}</p>
              </span>
            </div>

            <div className="warp-si-box">
              <h5>OS:</h5>
              <span className="warp-si-badge">
                {osLogo(s?.os_slug) ? <img src={osLogo(s?.os_slug) as string} alt="" /> : null}
                <span>{s?.os_name || "—"}</span>
              </span>
            </div>

            <div className="warp-si-box">
              <h5>Kernel:</h5>
              <span className="warp-si-badge">
                {s?.kernel ? `${s.kernel} (${s.arch})` : "—"}
              </span>
            </div>

            <div className="warp-si-box">
              <h5>Panel Version:</h5>
              <span className="warp-si-badge">
                <img
                  src={theme === "dark" ? "/warp/logo/WarpProxy_Logo_I_W.svg" : "/warp/logo/WarpProxy_Logo_I.svg"}
                  alt=""
                />
                <span>{s?.app_version ? `v${s.app_version}` : "—"}</span>
              </span>
            </div>

            <div className="warp-si-box">
              <h5>Status:</h5>
              <span className={`warp-si-badge ${s ? "warp-si-bg-green" : ""}`}>
                {s ? "Running" : "Offline"}
              </span>
              <button type="button" className="warp-si-badge warp-si-bg-blue" onClick={onRestart}>
                Restart
              </button>
            </div>

            <div className="warp-si-box">
              <h5>Uptime:</h5>
              <span className="warp-si-badge">{fmtUptime(s?.uptime_seconds ?? 0)}</span>
            </div>
          </div>
        </Card>

        <Card dot="span-yellow" title="Node Activity">
          {activity.length === 0 ? (
            <p className="warp-log-empty">No recent node activity.</p>
          ) : (
            <div className="warp-si-grid">
              {activity.map((n) => {
                const online = isNodeOnline(n.status);
                return (
                  <div key={n.id} className="warp-si-box">
                    <span className={`warp-node-chip ${online ? "warp-node-on" : "warp-node-off"}`} />
                    <span className="warp-si-ip">
                      <h4>{n.name}</h4>
                      <p>{n.host}:{n.port}</p>
                    </span>
                    <span className="warp-si-badge warp-node-time">{relativeTime(n.last_seen_at)}</span>
                  </div>
                );
              })}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
