import { apiFetch } from "./core";

export type WarpSettingsRead = {
  warp_enabled: boolean;
  warp_private_key: string;
  warp_public_key: string;
  warp_address: string;
  warp_endpoint: string;
  warp_reserved: string;
};

export function getWarpSettings() {
  return apiFetch<WarpSettingsRead>("/settings/warp");
}

export function updateWarpSettings(body: Partial<WarpSettingsRead>) {
  return apiFetch<WarpSettingsRead>("/settings/warp", {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}
