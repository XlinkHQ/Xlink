"use client";

import { useQuery } from "@tanstack/react-query";
import type { ApexOptions } from "apexcharts";
import { ArrowDown, ArrowUp, Clock, Cpu, HardDrive, MemoryStick, Monitor, Package, Podcast, Radio, RotateCw, Users, Zap } from "lucide-react";
import dynamic from "next/dynamic";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, listNodes, type NodeRead, restartPanel, systemStats, trafficSummary } from "@/lib/api";
import { toast } from "@/components/ui/toast";
import { isNodeOnline, relativeTime } from "@/lib/status";
import { baseAreaOptions, CHART_COLORS } from "@/shared/usage-chart";
import { toGiB } from "@/lib/format";
import { useTheme } from "@/lib/theme";

const OS_LOGOS: Record<string, string> = {
  ubuntu: "/warp/os/ubuntu.png",
  debian: "/warp/os/debian.png",
};
function osLogo(slug?: string): string | null {
  return OS_LOGOS[(slug ?? "").toLowerCase()] ?? null;
}

const ReactApexChart = dynamic(() => import("react-apexcharts"), { ssr: false });

function gb(v: number): string {
  return toGiB(v).toFixed(1);
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

const ICON_STROKE = 1.8;

function OverviewCard({
  title,
  right,
  children,
}: {
  title: string;
  right?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="warp-overview-card">
      <div className="warp-overview-head">
        <p className="warp-overview-title">{title}</p>
        {right ? <div className="warp-overview-right">{right}</div> : null}
      </div>
      <div className="warp-overview-divider" />
      {children}
    </div>
  );
}

function Stat({
  icon,
  label,
  count,
  sub,
  children,
}: {
  icon: ReactNode;
  label: string;
  count?: ReactNode;
  sub?: { label: string; value: string };
  children?: ReactNode;
}) {
  return (
    <div className="warp-stat">
      <div className="label">
        {icon}
        <span>{label}</span>
      </div>
      {count !== undefined ? <div className="count">{count}</div> : null}
      {sub ? (
        <div className="warp-stat-sub">
          <span>{sub.label}:</span>
          <span className="warp-stat-badge">{sub.value}</span>
        </div>
      ) : null}
      {children}
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

function ResourceCard({
  icon,
  title,
  status,
  pct,
  rows,
}: {
  icon: ReactNode;
  title: string;
  status: string;
  pct: number;
  rows: Array<[string, string]>;
}) {
  return (
    <div className="warp-overview-card warp-res-card">
      <div className="warp-overview-head">
        <p className="warp-overview-title">
          {icon}
          <span>{title}</span>
        </p>
        <span className="warp-res-status">{status}</span>
      </div>
      <div className="warp-overview-divider" />
      <div className="warp-res-pct">{Math.min(100, Math.max(0, pct))}%</div>
      <div className="warp-res-bar">
        <div className="warp-res-fill" style={{ width: `${Math.min(100, Math.max(0, pct))}%` }} />
      </div>
      <div className="warp-card-footer">
        {rows.map(([k, v]) => (
          <FootRow key={k} k={k} v={v} />
        ))}
      </div>
    </div>
  );
}

export function DashboardScreen() {
  const dark = useTheme() === "dark";
  const q = useQuery({ queryKey: ["system"], queryFn: () => systemStats(), refetchInterval: 1000, refetchIntervalInBackground: false });
  const nodesQ = useQuery({ queryKey: ["nodes"], queryFn: () => listNodes(), refetchInterval: 10000, refetchIntervalInBackground: false });
  const trafficQ = useQuery({ queryKey: ["traffic"], queryFn: () => trafficSummary(), refetchInterval: 10000, refetchIntervalInBackground: false });

  const s = q.data;
  const nodes = (nodesQ.data?.items ?? []) as NodeRead[];
  const t = trafficQ.data;

  const ramPct = s && s.ram_total_bytes > 0 ? Math.round((s.ram_used_bytes / s.ram_total_bytes) * 100) : 0;
  const diskPct = s && s.disk_total_bytes > 0 ? Math.round((s.disk_used_bytes / s.disk_total_bytes) * 100) : 0;
  const cpuPct = Math.round(s?.cpu_percent ?? 0);

  const WINDOW = 60;
  const [down, setDown] = useState<{ x: number; y: number }[]>([]);
  const [up, setUp] = useState<{ x: number; y: number }[]>([]);
  const prevTotals = useRef<{ d: number; u: number; at: number } | null>(null);
  useEffect(() => {
    if (!t) return;
    const now = trafficQ.dataUpdatedAt || Date.now();
    const dBytes = t.download_bytes;
    const uBytes = t.upload_bytes;
    const prev = prevTotals.current;
    prevTotals.current = { d: dBytes, u: uBytes, at: now };
    if (!prev) return;
    const dt = Math.max(1, (now - prev.at) / 1000);
    const dMbps = +((Math.max(0, dBytes - prev.d) * 8) / 1e6 / dt).toFixed(2);
    const uMbps = +((Math.max(0, uBytes - prev.u) * 8) / 1e6 / dt).toFixed(2);
    setDown((s) => [...s.slice(-(WINDOW - 1)), { x: now, y: dMbps }]);
    setUp((s) => [...s.slice(-(WINDOW - 1)), { x: now, y: uMbps }]);
  }, [trafficQ.dataUpdatedAt]);
  const hasThroughput = down.length > 0;

  const activity = useMemo(
    () =>
      [...nodes]
        .filter((n) => n.last_seen_at)
        .sort((a, b) => Date.parse(b.last_seen_at ?? "") - Date.parse(a.last_seen_at ?? ""))
        .slice(0, 12),
    [nodes],
  );

  const onlineNodes = useMemo(() => nodes.filter((n) => isNodeOnline(n.status)).length, [nodes]);

  const peakDown = useMemo(() => down.reduce((m, p) => Math.max(m, p.y), 0), [down]);
  const peakUp = useMemo(() => up.reduce((m, p) => Math.max(m, p.y), 0), [up]);

  const onRestart = async () => {
    try {
      await restartPanel();
      toast("success", "Panel is restarting…");
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Restart failed.");
    }
  };

  const fmtRate = (v: number) => (v >= 1000 ? `${(v / 1000).toFixed(2)} Gbps` : `${v.toFixed(1)} Mbps`);
  const chartBase = baseAreaOptions(dark, {
    height: 250,
    colors: [CHART_COLORS.accent, CHART_COLORS.danger],
  });
  const chartOptions: ApexOptions = {
    ...chartBase,
    chart: { ...chartBase.chart, id: "net-throughput" },
    xaxis: {
      ...chartBase.xaxis,
      labels: { ...(chartBase.xaxis as { labels?: object }).labels, format: "HH:mm:ss" },
    },
    yaxis: {
      ...chartBase.yaxis,
      forceNiceScale: true,
      labels: { ...(chartBase.yaxis as { labels?: object }).labels, formatter: (v) => fmtRate(v) },
    },
    tooltip: {
      ...chartBase.tooltip,
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
      <OverviewCard title="Overview">
        <div className="warp-stats-summary">
          <div className="warp-stats-track">
            <Stat
              icon={<Radio size={20} strokeWidth={ICON_STROKE} />}
              label="Nodes online"
              count={onlineNodes}
              sub={{ label: "Total nodes", value: `${nodes.length}` }}
            />
            <Stat
              icon={<Users size={20} strokeWidth={ICON_STROKE} />}
              label="Recent activity"
              count={activity.length}
            />
            <Stat icon={<ArrowUp size={20} strokeWidth={ICON_STROKE} />} label="Network usage">
              <div className="warp-transfer-bar download">
                <div className="left">
                  <ArrowDown size={20} strokeWidth={ICON_STROKE} />
                  <p>In</p>
                </div>
                <div className="right">{gb(t?.download_bytes ?? 0)} GiB</div>
              </div>
              <div className="warp-transfer-bar upload">
                <div className="left">
                  <ArrowUp size={20} strokeWidth={ICON_STROKE} />
                  <p>Out</p>
                </div>
                <div className="right">{gb(t?.upload_bytes ?? 0)} GiB</div>
              </div>
            </Stat>
          </div>

          <div className="warp-transfer-section">
            <div className="warp-transfer-top">
              <p>Network Traffic</p>
              <div className="right">
                <span className="peak">Peak</span>
                <span className="warp-peak-down">{fmtRate(peakDown)}</span>
                <span className="sep">/</span>
                <span className="warp-peak-up">{fmtRate(peakUp)}</span>
              </div>
            </div>
            {hasThroughput ? (
              <ReactApexChart options={chartOptions} series={chartSeries} type="area" height={250} />
            ) : (
              <div
                className="grid place-items-center text-sm text-fg-muted"
                style={{ height: 250 }}
              >
                Waiting for live traffic…
              </div>
            )}
          </div>
        </div>
      </OverviewCard>

      <div className="warp-grid-3">
        <ResourceCard
          icon={<Cpu size={16} strokeWidth={ICON_STROKE} />}
          title="CPU"
          status={s ? "Running" : "…"}
          pct={cpuPct}
          rows={[["Cores", `${s?.cpu_cores ?? 0}`], ["Processes", `${s?.process_count ?? 0}`], ["Load", `${(s?.load_avg_1 ?? 0).toFixed(2)}`]]}
        />
        <ResourceCard
          icon={<MemoryStick size={16} strokeWidth={ICON_STROKE} />}
          title="RAM"
          status={s ? "Running" : "…"}
          pct={ramPct}
          rows={[["Used", `${gb(s?.ram_used_bytes ?? 0)} GiB`], ["Total", `${gb(s?.ram_total_bytes ?? 0)} GiB`], ["Free", `${gb(Math.max(0, (s?.ram_total_bytes ?? 0) - (s?.ram_used_bytes ?? 0)))} GiB`]]}
        />
        <ResourceCard
          icon={<HardDrive size={16} strokeWidth={ICON_STROKE} />}
          title="Disk"
          status={s ? "Running" : "…"}
          pct={diskPct}
          rows={[["Used", `${gb(s?.disk_used_bytes ?? 0)} GiB`], ["Total", `${gb(s?.disk_total_bytes ?? 0)} GiB`], ["Swap", `${gb(s?.swap_used_bytes ?? 0)} GiB`]]}
        />
      </div>

      <div className="warp-grid-2">
        <OverviewCard title="System Info">
          <div className="warp-si-grid">
            <div className="warp-si-box">
              <Podcast className="warp-si-rowicon" size={15} aria-hidden />
              <span className="warp-si-ip">
                <h4>{s?.ip_address || "—"}</h4>
                <p>{s?.ip6_address || s?.mac_address || "—"}</p>
              </span>
            </div>

            <div className="warp-si-box">
              <Monitor className="warp-si-rowicon" size={15} aria-hidden />
              <h5>OS</h5>
              <span className="warp-si-badge">
                {osLogo(s?.os_slug) ? <img src={osLogo(s?.os_slug) as string} alt="" /> : null}
                <span>{s?.os_name || "—"}</span>
              </span>
            </div>

            <div className="warp-si-box">
              <Cpu className="warp-si-rowicon" size={15} aria-hidden />
              <h5>Kernel</h5>
              <span className="warp-si-badge">
                {s?.kernel ? `${s.kernel} (${s.arch})` : "—"}
              </span>
            </div>

            <div className="warp-si-box">
              <Package className="warp-si-rowicon" size={15} aria-hidden />
              <h5>Panel Version</h5>
              <span className="warp-si-badge">
                <span>{s?.app_version ? `v${s.app_version}` : "—"}</span>
              </span>
            </div>

            <div className="warp-si-box">
              <Zap className="warp-si-rowicon" size={15} aria-hidden />
              <h5>Status</h5>
              <span className={`warp-si-status ${s ? "is-on" : "is-off"}`}>
                {s ? "Running" : "Offline"}
              </span>
              <button type="button" className="warp-si-restart" onClick={onRestart}>
                <RotateCw size={13} aria-hidden /> Restart
              </button>
            </div>

            <div className="warp-si-box">
              <Clock className="warp-si-rowicon" size={15} aria-hidden />
              <h5>Uptime</h5>
              <span className="warp-si-badge">{fmtUptime(s?.uptime_seconds ?? 0)}</span>
            </div>
          </div>
        </OverviewCard>

        <OverviewCard title="Node Activity">
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
        </OverviewCard>
      </div>
    </div>
  );
}
