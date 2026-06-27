import { createElement } from "react";
import type { ReactElement, ReactNode, SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & {
  size?: number | string;
};
type NavIcon = (props: IconProps) => ReactElement;
type NavItem = { key: string; label: string; icon: NavIcon };
type NavGroup = { title?: string; items: NavItem[] };

function path(d: string, extra?: Record<string, string>) {
  return createElement("path", { d, ...extra });
}

function FilledIcon({ children, size = 16, ...props }: IconProps) {
  return createElement(
    "svg",
    {
      width: size,
      height: size,
      viewBox: "0 0 16 16",
      role: "img",
      focusable: "false",
      "aria-hidden": true,
      xmlns: "http://www.w3.org/2000/svg",
      fill: "currentColor",
      ...props,
    },
    children as ReactNode,
  );
}

function OverviewIcon(props: IconProps) {
  return FilledIcon({
    ...props,
    children: [
      path("M8 6a2 2 0 1 1 0 4 2 2 0 0 1 0-4Z", { key: "a" }),
      path("M10.75 1 12.25 1.003A2.75 2.75 0 0 1 15 3.753V5.25a.75.75 0 0 1-1.5 0V3.753a1.25 1.25 0 0 0-1.252-1.25L10.749 2.5A.75.75 0 0 1 10.75 1ZM5.25 1A.75.75 0 0 1 5.251 2.5l-1.499.003A1.25 1.25 0 0 0 2.504 3.753V5.25a.75.75 0 0 1-1.5 0V3.753A2.75 2.75 0 0 1 3.75 1.003L5.25 1ZM1.75 10a.75.75 0 0 1 .75.75v1.497a1.25 1.25 0 0 0 1.248 1.25L5.247 13.5A.75.75 0 1 1 5.245 15l-1.5-.003A2.75 2.75 0 0 1 1 12.247V10.75A.75.75 0 0 1 1.75 10ZM14.246 10a.75.75 0 0 1 .75.75v1.497a2.75 2.75 0 0 1-2.745 2.75L10.751 15A.75.75 0 1 1 10.749 13.5l1.5-.003a1.25 1.25 0 0 0 1.247-1.25V10.75a.75.75 0 0 1 .75-.75Z", { key: "b" }),
    ],
  });
}

function NodesIcon(props: IconProps) {
  return FilledIcon({
    ...props,
    children: [
      path("M6.932 2.214a2.75 2.75 0 0 1 2.282.066l5.066 2.467c.944.46.964 1.812.034 2.3L9.287 9.683a2.75 2.75 0 0 1-2.574 0L1.686 7.047c-.93-.488-.91-1.84.034-2.3l5.066-2.467.146-.066ZM8.551 3.671a1.25 1.25 0 0 0-1.103 0L2.839 5.914l4.576 2.398c.367.193.803.193 1.17 0l4.574-2.398-4.608-2.243Z", { key: "a", fillRule: "evenodd", clipRule: "evenodd" }),
      path("M13.905 10.077a.75.75 0 0 1 .691 1.2l-5.097 2.392a3.5 3.5 0 0 1-2.998 0l-5.097-2.392a.75.75 0 1 1 .692-1.2l5.096 2.391a2 2 0 0 0 1.616 0l5.097-2.391Z", { key: "b", fillRule: "evenodd", clipRule: "evenodd" }),
    ],
  });
}

function HostsIcon(props: IconProps) {
  return FilledIcon({
    ...props,
    children: [
      path("M8.154 1.004A3.004 3.004 0 0 1 11 4v4a3 3 0 0 1-3 3H4a3 3 0 0 1-3-3V4a3 3 0 0 1 3-3h4l.154.004ZM4 2.5A1.5 1.5 0 0 0 2.5 4v4A1.5 1.5 0 0 0 4 9.5h4A1.5 1.5 0 0 0 9.5 8V4A1.5 1.5 0 0 0 8 2.5H4Z", { key: "a", fillRule: "evenodd", clipRule: "evenodd" }),
      path("M13.25 5.25A1.75 1.75 0 0 1 15 7v4.75A3.25 3.25 0 0 1 11.75 15h-5A1.75 1.75 0 0 1 5 13.25a.75.75 0 0 1 1.5 0c0 .138.112.25.25.25h5a1.75 1.75 0 0 0 1.75-1.75V7a.25.25 0 0 0-.25-.25.75.75 0 0 1 0-1.5Z", { key: "b", fillRule: "evenodd", clipRule: "evenodd" }),
    ],
  });
}

function ServicesIcon(props: IconProps) {
  return FilledIcon({
    ...props,
    children: path("M4.986 1.009 5.19 1h5.612l.205.009a2.5 2.5 0 0 1 2.187 1.771l1.697 5.649c.112.375.135.772.066 1.158l-.45 2.527-.07.308A3.5 3.5 0 0 1 11.062 15H4.929a3.5 3.5 0 0 1-3.374-2.578l-.07-.308-.451-2.527a2.5 2.5 0 0 1 .067-1.158l1.696-5.649A2.5 2.5 0 0 1 4.986 1.009ZM2.961 11.852A2 2 0 0 0 4.929 13.5h6.133a2 2 0 0 0 1.969-1.648l.241-1.352h-1.651a1.35 1.35 0 0 0-1.128.604A2.01 2.01 0 0 1 8.819 12H7.172a2.01 2.01 0 0 1-1.674-.896A1.35 1.35 0 0 0 4.371 10.5H2.72l.241 1.352ZM5.19 2.5a1 1 0 0 0-.958.712L2.537 8.86A1 1 0 0 0 2.507 9H4.37a2.85 2.85 0 0 1 2.413 1.322.5.5 0 0 0 .388.178H8.82a.5.5 0 0 0 .427-.228A2.85 2.85 0 0 1 11.621 9h1.864a1 1 0 0 0-.03-.14l-1.696-5.648a1 1 0 0 0-.957-.712H5.19Z", { fillRule: "evenodd", clipRule: "evenodd" }),
  });
}

function UsersIcon(props: IconProps) {
  return FilledIcon({
    ...props,
    children: [
      path("M8 2.25A2.75 2.75 0 1 1 8 7.75 2.75 2.75 0 0 1 8 2.25ZM3 12.15C3 10.41 5.028 9 8 9s5 1.41 5 3.15v.35c0 .828-.672 1.5-1.5 1.5h-7A1.5 1.5 0 0 1 3 12.5v-.35Z", { key: "a" }),
      path("M12.35 3.45a2.2 2.2 0 0 1 .9 4.11.75.75 0 0 1-.658-1.348.7.7 0 0 0-.287-1.337.75.75 0 0 1 .045-1.425ZM13.35 9.3c1.36.36 2.15 1.136 2.15 2.15v.2a1.35 1.35 0 0 1-1.35 1.35h-.4a.75.75 0 0 1 0-1.5h.25v-.05c0-.26-.43-.55-1.035-.71a.75.75 0 0 1 .385-1.44Z", { key: "b", opacity: ".76" }),
    ],
  });
}

function AdminsIcon(props: IconProps) {
  return FilledIcon({
    ...props,
    children: path("M7.7 1.12a.75.75 0 0 1 .6 0l4.75 2.05a.75.75 0 0 1 .45.689V7.25c0 3.195-2.051 5.959-5.203 7.67a.75.75 0 0 1-.714 0C4.401 13.21 2.5 10.445 2.5 7.25V3.859a.75.75 0 0 1 .453-.689L7.7 1.12ZM10.78 6.53a.75.75 0 0 0-1.06-1.06L7.25 7.94 6.28 6.97a.75.75 0 0 0-1.06 1.06l1.5 1.5a.75.75 0 0 0 1.06 0l3-3Z", { fillRule: "evenodd", clipRule: "evenodd" }),
  });
}

function SettingsIcon(props: IconProps) {
  return FilledIcon({
    ...props,
    children: [
      path("M4 3.25h8a.75.75 0 0 1 0 1.5H4a.75.75 0 0 1 0-1.5ZM2.75 7.25h10.5a.75.75 0 0 1 0 1.5H2.75a.75.75 0 0 1 0-1.5ZM5 11.25h6a.75.75 0 0 1 0 1.5H5a.75.75 0 0 1 0-1.5Z", { key: "a" }),
      path("M5.5 2.25a2 2 0 1 1 0 4 2 2 0 0 1 0-4ZM10.5 6.25a2 2 0 1 1 0 4 2 2 0 0 1 0-4ZM7.5 10.25a2 2 0 1 1 0 4 2 2 0 0 1 0-4Z", { key: "b" }),
    ],
  });
}

export function SearchIcon(props: IconProps) {
  return FilledIcon({
    ...props,
    children: path("M7.25 1.5a5.75 5.75 0 0 1 4.58 9.228l2.971 2.971a.75.75 0 0 1-1.06 1.061l-2.972-2.971A5.75 5.75 0 1 1 7.25 1.5Zm0 1.5a4.25 4.25 0 1 0 0 8.5 4.25 4.25 0 0 0 0-8.5Z", { fillRule: "evenodd", clipRule: "evenodd" }),
  });
}

export function LogoutIcon(props: IconProps) {
  return FilledIcon({
    ...props,
    children: path("M2.75 2A1.75 1.75 0 0 0 1 3.75v8.5C1 13.216 1.784 14 2.75 14h4.5a.75.75 0 0 0 0-1.5h-4.5a.25.25 0 0 1-.25-.25v-8.5a.25.25 0 0 1 .25-.25h4.5a.75.75 0 0 0 0-1.5h-4.5Zm8.72 3.22a.75.75 0 0 1 1.06 0l2.25 2.25a.75.75 0 0 1 0 1.06l-2.25 2.25a.75.75 0 1 1-1.06-1.06l.97-.97H6.75a.75.75 0 0 1 0-1.5h5.69l-.97-.97a.75.75 0 0 1 0-1.06Z", { fillRule: "evenodd", clipRule: "evenodd" }),
  });
}

export function SunIcon(props: IconProps) {
  return FilledIcon({
    ...props,
    children: path("M8 4.25A3.75 3.75 0 1 1 8 11.75 3.75 3.75 0 0 1 8 4.25ZM8 .75a.75.75 0 0 1 .75.75v1a.75.75 0 0 1-1.5 0v-1A.75.75 0 0 1 8 .75ZM8 12.75a.75.75 0 0 1 .75.75v1a.75.75 0 0 1-1.5 0v-1a.75.75 0 0 1 .75-.75ZM1.5 7.25h1a.75.75 0 0 1 0 1.5h-1a.75.75 0 0 1 0-1.5ZM13.5 7.25h1a.75.75 0 0 1 0 1.5h-1a.75.75 0 0 1 0-1.5ZM3.05 3.05a.75.75 0 0 1 1.061 0l.707.707a.75.75 0 0 1-1.06 1.061l-.708-.707a.75.75 0 0 1 0-1.061ZM11.182 11.182a.75.75 0 0 1 1.06 0l.708.707a.75.75 0 0 1-1.061 1.061l-.707-.707a.75.75 0 0 1 0-1.06ZM12.95 3.05a.75.75 0 0 1 0 1.061l-.707.707a.75.75 0 1 1-1.061-1.06l.707-.708a.75.75 0 0 1 1.061 0ZM4.818 11.182a.75.75 0 0 1 0 1.06l-.707.708A.75.75 0 1 1 3.05 11.89l.707-.707a.75.75 0 0 1 1.061 0Z"),
  });
}

export function MoonIcon(props: IconProps) {
  return FilledIcon({
    ...props,
    children: path("M9.592 1.244a.75.75 0 0 1 .745.982A5.5 5.5 0 0 0 13.774 9.663a.75.75 0 0 1 .213 1.307A7 7 0 1 1 5.03 2.013a.75.75 0 0 1 1.307.213 5.5 5.5 0 0 0 3.255-.982Z"),
  });
}

export const NAV_GROUPS: NavGroup[] = [
  {
    items: [{ key: "Overview", label: "Overview", icon: OverviewIcon }],
  },
  {
    title: "Network",
    items: [
      { key: "Nodes", label: "Nodes", icon: NodesIcon },
      { key: "Profiles", label: "Hosts", icon: HostsIcon },
      { key: "Groups", label: "Services", icon: ServicesIcon },
    ],
  },
  {
    title: "Management",
    items: [
      { key: "Users", label: "Users", icon: UsersIcon },
      { key: "Admins", label: "Admins", icon: AdminsIcon },
    ],
  },
  {
    title: "System",
    items: [{ key: "Settings", label: "Settings", icon: SettingsIcon }],
  },
];

export const NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap((g) => g.items);
