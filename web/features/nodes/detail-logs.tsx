"use client";

import { useQuery } from "@tanstack/react-query";
import { type ReactNode } from "react";
import { nodeLogs } from "@/lib/api";

export function NodeLogs({ nodeId, source }: { nodeId: string; source?: string }) {
  const q = useQuery({
    queryKey: ["node-logs", nodeId, source ?? "all"],
    queryFn: () => nodeLogs(nodeId, 100, source),
    refetchInterval: 10000,
    refetchIntervalInBackground: false,
  });
  const logs = q.data ?? [];

  const parse = (l: Record<string, unknown>) => {
    const msgRaw = l.message ?? l.msg ?? l.line ?? l.text;
    const msg = typeof msgRaw === "string" ? msgRaw : JSON.stringify(l);
    const lvlRaw = String(l.level ?? l.severity ?? "");
    const lvl = lvlRaw.toLowerCase().replace(/[[\]]/g, "");
    const tsRaw = l.ts ?? l.timestamp ?? l.time;
    const ts = typeof tsRaw === "string" ? tsRaw.slice(11, 19) : "";
    return { ts, lvl, msg };
  };

  const lvlTone = (lvl: string) =>
    lvl.includes("error") ? "err" : lvl.includes("warn") ? "warn" : lvl.includes("debug") ? "dim" : "info";

  const renderMsg = (msg: string) => {
    const re =
      /(\baccepted\b|\brejected\b|\bblocked\b)|(\b\d{1,3}(?:\.\d{1,3}){3}:\d+\b)|(\b\d{1,3}(?:\.\d{1,3}){3}\b)|(\b(?:tcp|udp):[^\s]+)|(email:\s*[^\s]+)|(->|>>)/g;
    const out: ReactNode[] = [];
    let last = 0;
    let m: RegExpExecArray | null;
    let k = 0;
    while ((m = re.exec(msg)) !== null) {
      if (m.index > last) out.push(msg.slice(last, m.index));
      let cls = "lg-dim";
      if (m[1]) cls = m[1] === "accepted" ? "lg-accept" : "lg-rej";
      else if (m[2]) cls = "lg-addr";
      else if (m[3]) cls = "lg-ip";
      else if (m[4]) cls = "lg-dest";
      else if (m[5]) cls = "lg-email";
      else if (m[6]) cls = "lg-arrow";
      out.push(
        <span key={k++} className={cls}>
          {m[0]}
        </span>,
      );
      last = m.index + m[0].length;
    }
    if (last < msg.length) out.push(msg.slice(last));
    return out;
  };

  return (
    <div>
      <pre className="warp-logs-pre">
        {q.isLoading ? (
          "Loading…"
        ) : logs.length === 0 ? (
          "No logs reported by this node yet."
        ) : (
          logs.map((l, i) => {
            const { ts, lvl, msg } = parse(l);
            return (
              <div key={i} className="warp-log-line">
                {ts ? <span className="warp-log-ts">{ts}</span> : null}
                {lvl ? <span className={`warp-log-lvl ${lvlTone(lvl)}`}>[{lvl}]</span> : null}
                <span className="warp-log-msg">{renderMsg(msg)}</span>
              </div>
            );
          })
        )}
      </pre>
    </div>
  );
}
