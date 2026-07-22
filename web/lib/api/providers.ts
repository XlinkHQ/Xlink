import { apiFetch } from "./core";

export type ProviderRead = {
  name: string;
  kind: string;
  version: string;
  capabilities: string[];
};

export function listProviders() {
  return apiFetch<ProviderRead[]>("/providers");
}
