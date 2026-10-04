import type { ReactElement } from "react";
import type { MessageKey } from "@/lib/i18n";
import {
  DgAccessSettings,
  DgActivity,
  DgGateway,
  DgGlobe,
  DgGroups,
  DgKeyIcon,
  DgPieChart,
  DgRules,
  DgSettings,
  DgUsers,
  DgWebhooks,
} from "./dg-icons";

type NavIcon = (props: { size?: number }) => ReactElement;
export type NavItem = { key: string; labelKey: MessageKey; icon: NavIcon };
export type NavGroup = { titleKey?: MessageKey; items: NavItem[] };

export const NAV_GROUPS: NavGroup[] = [
  {
    titleKey: "navgroup.vpn",
    items: [{ key: "Overview", labelKey: "nav.overview", icon: DgPieChart }],
  },
  {
    titleKey: "navgroup.network",
    items: [
      { key: "Nodes", labelKey: "nav.nodes", icon: DgGlobe },
      { key: "Profiles", labelKey: "nav.hosts", icon: DgGateway },
      { key: "Groups", labelKey: "nav.services", icon: DgAccessSettings },
      { key: "Routing", labelKey: "nav.routing", icon: DgRules },
      { key: "Outbounds", labelKey: "nav.outbounds", icon: DgWebhooks },
    ],
  },
  {
    titleKey: "navgroup.management",
    items: [
      { key: "Users", labelKey: "nav.users", icon: DgUsers },
      { key: "Admins", labelKey: "nav.admins", icon: DgGroups },
      { key: "Roles", labelKey: "nav.roles", icon: DgAccessSettings },
      { key: "Activity", labelKey: "nav.activity", icon: DgActivity },
    ],
  },
  {
    titleKey: "navgroup.system",
    items: [
      { key: "ApiKeys", labelKey: "nav.apiKeys", icon: DgKeyIcon },
      { key: "ClientTemplates", labelKey: "nav.clientTemplates", icon: DgRules },
      { key: "Settings", labelKey: "nav.settings", icon: DgSettings },
    ],
  },
];

export const NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap((g) => g.items);
