import { apiFetch } from "./core";

export type SubscriptionRuleResult =
  | "links"
  | "base64"
  | "xray"
  | "singbox"
  | "clash"
  | "clash-meta"
  | "block";

export type SubscriptionRule = {
  pattern: string;
  result: SubscriptionRuleResult;
};

export type SubscriptionSettings = {
  profile_title: string;
  support_link: string;
  update_interval_hours: number;
  active_status_text: string;
  expired_status_text: string;
  limited_status_text: string;
  disabled_status_text: string;
  onhold_status_text: string;
  config_remark: string;
  shuffle_configs: boolean;
  placeholder_if_disabled: boolean;
  placeholder_remark: string;
  custom_page_html: string;
  rules: SubscriptionRule[];
};

export function getSubscriptionSettings() {
  return apiFetch<SubscriptionSettings>("/settings/subscription");
}

export function updateSubscriptionSettings(body: Partial<SubscriptionSettings>) {
  return apiFetch<SubscriptionSettings>("/settings/subscription", {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function userSubscriptionUrl(userId: string) {
  return apiFetch<{ token: string; subscription_url: string }>(
    `/subscriptions/users/${userId}/token`,
  );
}
