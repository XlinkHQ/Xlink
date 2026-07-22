"use client";

import { useQuery } from "@tanstack/react-query";
import { listNodes, onlineUsers, usersTotal } from "@/lib/api";
import { isNodeOnline } from "@/lib/status";

export function useConsoleStats() {
  const onlineQuery = useQuery({
    queryKey: ["topbar-online-users"],
    queryFn: () => onlineUsers(),
    refetchInterval: 30000,
    refetchIntervalInBackground: false,
  });
  const usersQuery = useQuery({
    queryKey: ["topbar-users-total"],
    queryFn: () => usersTotal("user"),
    refetchInterval: 30000,
    refetchIntervalInBackground: false,
  });
  const nodesQuery = useQuery({
    queryKey: ["nodes"],
    queryFn: () => listNodes(),
    refetchInterval: 30000,
    refetchIntervalInBackground: false,
  });

  const totalUsers = usersQuery.data ? usersQuery.data.meta.total : null;
  const onlineUsersCount = onlineQuery.data ? onlineQuery.data.user_ids.length : null;

  const nodeItems = nodesQuery.data?.items ?? null;
  const totalNodes = nodeItems ? nodeItems.length : null;
  const onlineNodes = nodeItems ? nodeItems.filter((n) => isNodeOnline(n.status)).length : null;

  return { totalUsers, onlineUsersCount, totalNodes, onlineNodes };
}
