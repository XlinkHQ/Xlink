import type { ReactElement } from "react";
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
export type NavItem = { key: string; label: string; icon: NavIcon };
export type NavGroup = { title?: string; items: NavItem[] };

export const NAV_GROUPS: NavGroup[] = [
  {
    title: "VPN",
    items: [{ key: "Overview", label: "Overview", icon: DgPieChart }],
  },
  {
    title: "Network",
    items: [
      { key: "Nodes", label: "Nodes", icon: DgGlobe },
      { key: "Profiles", label: "Hosts", icon: DgGateway },
      { key: "Groups", label: "Services", icon: DgAccessSettings },
      { key: "Routing", label: "Routing", icon: DgRules },
      { key: "Outbounds", label: "Outbounds", icon: DgWebhooks },
    ],
  },
  {
    title: "Management",
    items: [
      { key: "Users", label: "Users", icon: DgUsers },
      { key: "Admins", label: "Admins", icon: DgGroups },
      { key: "Activity", label: "Activity log", icon: DgActivity },
    ],
  },
  {
    title: "System",
    items: [
      { key: "ApiKeys", label: "API Keys", icon: DgKeyIcon },
      { key: "Settings", label: "Settings", icon: DgSettings },
    ],
  },
];

export const NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap((g) => g.items);
