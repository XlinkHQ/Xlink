import { apiFetch } from "./core";

export function getCoreTemplates() {
  return apiFetch<{ templates: Record<string, string> }>("/settings/core");
}

export function updateCoreTemplate(core: string, template: string) {
  return apiFetch<{ templates: Record<string, string> }>("/settings/core", {
    method: "PUT",
    body: JSON.stringify({ core, template }),
  });
}

export type NotificationSettingsRead = {
  notify_enabled: boolean;
  notify_expiring_days: number;
  notify_usage_percent: number;
  notify_node_down: boolean;
  webhook_address: string;
  discord_webhook_url: string;
  telegram_bot_token: string;
  telegram_chat_ids: string;
};

export function getNotificationSettings() {
  return apiFetch<NotificationSettingsRead>("/settings/notifications");
}

export function updateNotificationSettings(body: Partial<NotificationSettingsRead>) {
  return apiFetch<NotificationSettingsRead>("/settings/notifications", {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function testNotificationSettings(body: Partial<NotificationSettingsRead>) {
  return apiFetch<{ status: string }>("/settings/notifications/test", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
