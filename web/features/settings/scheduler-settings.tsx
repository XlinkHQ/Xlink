"use client";

import { useQuery } from "@tanstack/react-query";
import { Route } from "lucide-react";
import { useEffect, useState } from "react";
import { Select } from "@/components/ui/input";
import { toast } from "@/components/ui/toast";
import {
  ApiError,
  listNodes,
  listProfiles,
  schedulerPolicies,
  schedulerRun,
  type ProfileRead,
  type SchedulerDecisionRead,
} from "@/lib/api";
import { useT } from "@/lib/i18n";
import { SettingsRow } from "./save-context";
import { SettingsSection } from "@/shared/settings-kit";

export function SchedulerSettingsScreen() {
  const t = useT();
  const profilesQ = useQuery({ queryKey: ["profiles"], queryFn: () => listProfiles() });
  const policiesQ = useQuery({ queryKey: ["scheduler-policies"], queryFn: () => schedulerPolicies() });
  const nodesQ = useQuery({ queryKey: ["nodes"], queryFn: () => listNodes({ size: 200 }) });
  const profiles = (profilesQ.data?.items ?? []) as ProfileRead[];
  const policies = policiesQ.data ?? [];
  const nodeName = (id: string) => nodesQ.data?.items.find((n) => n.id === id)?.name ?? id.slice(0, 8);

  const [profileId, setProfileId] = useState("");
  const [policy, setPolicy] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<SchedulerDecisionRead | null>(null);

  useEffect(() => {
    if (!profileId && profiles.length) setProfileId(profiles[0].id);
  }, [profiles, profileId]);
  useEffect(() => {
    if (!policy && policies.length) setPolicy(policies[0]);
  }, [policies, policy]);

  const run = async () => {
    if (!profileId || !policy) return;
    setBusy(true);
    try {
      setResult(await schedulerRun({ profile_id: profileId, policy, dry_run: true }));
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("scheduler.runFailed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="w-full">
      <SettingsSection
        icon={Route}
        title={t("scheduler.title")}
        description={t("scheduler.description")}
      >
        <SettingsRow label={t("scheduler.profile")} hint={t("scheduler.profileHint")}>
          <Select value={profileId} onChange={(e) => setProfileId(e.target.value)}>
            {profiles.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </Select>
        </SettingsRow>
        <SettingsRow label={t("scheduler.policy")} hint={t("scheduler.policyHint")}>
          <Select value={policy} onChange={(e) => setPolicy(e.target.value)}>
            {policies.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </Select>
        </SettingsRow>
        <SettingsRow label={t("scheduler.simulate")} hint={t("scheduler.simulateHint")}>
          <button
            type="button"
            className="warp-tb-button warp-tb-button-primary"
            onClick={run}
            disabled={busy || !profileId || !policy}
          >
            {busy ? t("scheduler.running") : t("scheduler.runDryRun")}
          </button>
        </SettingsRow>
      </SettingsSection>

      {result ? (
        <SettingsSection
          divider
          icon={Route}
          title={t("scheduler.result")}
          description={t("scheduler.resultSummary", { node: nodeName(result.node_id), policy: result.policy, score: result.score.toFixed(2) })}
        >
          <div className="warp-sched-list">
            {result.candidates.map((c) => (
              <div
                key={c.node_id}
                className={`warp-sched-row ${c.node_id === result.node_id ? "is-chosen" : ""}`}
              >
                <div className="warp-sched-head">
                  <span className="warp-sched-name">{nodeName(c.node_id)}</span>
                  {c.node_id === result.node_id ? (
                    <span className="warp-badge success">{t("scheduler.chosen")}</span>
                  ) : null}
                  <span className="warp-sched-score">{c.score.toFixed(2)}</span>
                </div>
                {c.reasons.length ? (
                  <ul className="warp-sched-reasons">
                    {c.reasons.map((r, i) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ))}
          </div>
        </SettingsSection>
      ) : null}
    </div>
  );
}
