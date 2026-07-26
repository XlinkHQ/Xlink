"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "@/components/ui/toast";
import {
  getNotificationSettings,
  testNotificationSettings,
  updateNotificationSettings,
  ApiError,
  type NotificationSettingsRead,
} from "@/lib/api";
import { useT } from "@/lib/i18n";
import { SettingsRow, useRegisterSave } from "./save-context";
import { SettingsSection } from "@/shared/settings-kit";

const EMPTY: NotificationSettingsRead = {
  notify_enabled: true,
  notify_expiring_days: 3,
  notify_usage_percent: 80,
  notify_node_down: true,
  webhook_address: "",
  discord_webhook_url: "",
  telegram_bot_token: "",
  telegram_chat_ids: "",
};

export function NotificationsSettingsScreen() {
  const t = useT();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["notification-settings"], queryFn: () => getNotificationSettings() });
  const [form, setForm] = useState<NotificationSettingsRead>(EMPTY);
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const sendTest = async () => {
    setTesting(true);
    try {
      await testNotificationSettings(form);
      toast("success", t("notifications.testSent"));
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("notifications.testFailed"));
    } finally {
      setTesting(false);
    }
  };

  useEffect(() => {
    if (q.data && !loaded) {
      setForm(q.data);
      setLoaded(true);
    }
  }, [q.data, loaded]);

  const set = <K extends keyof NotificationSettingsRead>(k: K, v: NotificationSettingsRead[K]) =>
    setForm((f) => ({ ...f, [k]: v }));

  useRegisterSave(async () => {
    setBusy(true);
    try {
      const saved = await updateNotificationSettings(form);
      setForm(saved);
      qc.invalidateQueries({ queryKey: ["notification-settings"] });
      toast("success", t("notifications.saved"));
    } catch (e) {
      toast("error", e instanceof Error ? e.message : t("common.saveFailed"));
    } finally {
      setBusy(false);
    }
  }, busy);

  return (
    <div className="w-full">
      <SettingsSection
        icon={Bell}
        title={t("notifications.alertsTitle")}
        description={t("notifications.alertsDesc")}
      >
        <SettingsRow label={t("notifications.enable")} hint={t("notifications.enableHint")}>
          <label className="warp-switch">
            <input
              type="checkbox"
              checked={form.notify_enabled}
              onChange={(e) => set("notify_enabled", e.target.checked)}
            />
            <span className="warp-switch-track" />
          </label>
        </SettingsRow>
        <SettingsRow label={t("notifications.expiryWarning")} hint={t("notifications.expiryWarningHint")}>
          <input
            type="number"
            min={0}
            max={365}
            className="warp-set-input"
            value={form.notify_expiring_days}
            onChange={(e) => set("notify_expiring_days", Math.max(0, Number(e.target.value) || 0))}
          />
        </SettingsRow>
        <SettingsRow label={t("notifications.usageWarning")} hint={t("notifications.usageWarningHint")}>
          <input
            type="number"
            min={1}
            max={100}
            className="warp-set-input"
            value={form.notify_usage_percent}
            onChange={(e) =>
              set("notify_usage_percent", Math.min(100, Math.max(1, Number(e.target.value) || 1)))
            }
          />
        </SettingsRow>
        <SettingsRow label={t("notifications.nodeDown")} hint={t("notifications.nodeDownHint")}>
          <label className="warp-switch">
            <input
              type="checkbox"
              checked={form.notify_node_down}
              onChange={(e) => set("notify_node_down", e.target.checked)}
            />
            <span className="warp-switch-track" />
          </label>
        </SettingsRow>
      </SettingsSection>

      <SettingsSection
        divider
        icon={Bell}
        title={t("notifications.channelsTitle")}
        description={t("notifications.channelsDesc")}
      >
        <SettingsRow label={t("notifications.webhookUrls")} hint={t("notifications.webhookUrlsHint")}>
          <input
            className="warp-set-input warp-set-input-wide"
            placeholder="https://example.com/hook"
            value={form.webhook_address}
            onChange={(e) => set("webhook_address", e.target.value)}
          />
        </SettingsRow>
        <SettingsRow label={t("notifications.discordWebhook")} hint={t("notifications.discordWebhookHint")}>
          <input
            className="warp-set-input warp-set-input-wide"
            placeholder="https://discord.com/api/webhooks/…"
            value={form.discord_webhook_url}
            onChange={(e) => set("discord_webhook_url", e.target.value)}
          />
        </SettingsRow>
        <SettingsRow label={t("notifications.telegramBotToken")} hint={t("notifications.telegramBotTokenHint")}>
          <input
            className="warp-set-input warp-set-input-wide"
            placeholder="123456:ABC…"
            value={form.telegram_bot_token}
            onChange={(e) => set("telegram_bot_token", e.target.value)}
          />
        </SettingsRow>
        <SettingsRow label={t("notifications.telegramChatIds")} hint={t("notifications.telegramChatIdsHint")}>
          <input
            className="warp-set-input warp-set-input-wide"
            placeholder="-1001234567890"
            value={form.telegram_chat_ids}
            onChange={(e) => set("telegram_chat_ids", e.target.value)}
          />
        </SettingsRow>
        <SettingsRow label={t("notifications.testDelivery")} hint={t("notifications.testDeliveryHint")}>
          <button type="button" className="warp-tb-button" onClick={sendTest} disabled={testing}>
            {testing ? t("notifications.sending") : t("notifications.sendTest")}
          </button>
        </SettingsRow>
      </SettingsSection>
    </div>
  );
}
