import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api";
import type { BoardDetail, CreateBoardBody } from "@/api/endpoints/board";

export const boardKeys = {
  all: ["board"] as const,
  list: () => ["board", "list"] as const,
  detail: (id: number) => ["board", "detail", id] as const,
};

export function useBoards() {
  return useQuery({
    queryKey: boardKeys.list(),
    queryFn: ({ signal }) => api.board.list(signal),
  });
}

export function useBoardDetail(boardId: number | null) {
  return useQuery({
    queryKey: boardId ? boardKeys.detail(boardId) : ["board", "detail", "none"],
    queryFn: ({ signal }) => api.board.get(boardId as number, signal),
    enabled: boardId != null,
  });
}

export function useCreateBoard() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateBoardBody) => api.board.create(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: boardKeys.list() }),
  });
}

export function useInvalidateBoard(boardId: number | null) {
  const qc = useQueryClient();
  return () => {
    if (boardId != null) qc.invalidateQueries({ queryKey: boardKeys.detail(boardId) });
  };
}

/**
 * Ephemeral presence: send a throttled heartbeat with the current selection and
 * poll the active roster. Stored server-side in NoSQL with a short TTL; never in
 * the append-only activity history.
 */
export function useBoardPresence(
  boardId: number | null,
  selection: { kind: string | null; id: number | null },
  enabled = true,
) {
  const rosterRef = useRef<{ count: number; actors: string[] }>({ count: 0, actors: [] });
  const [, force] = useState(0);
  useEffect(() => {
    if (!boardId || !enabled) return;
    let alive = true;
    const beat = async () => {
      try {
        const r = await api.board.presenceBeat(boardId, {
          selection: selection.id != null ? { kind: selection.kind, id: selection.id } : undefined,
        });
        if (!alive) return;
        rosterRef.current = { count: r.count, actors: r.actors.map((a) => a.actor) };
        force((n) => n + 1);
      } catch {
        /* transient */
      }
    };
    beat();
    const h = window.setInterval(beat, 5000);
    return () => {
      alive = false;
      window.clearInterval(h);
    };
  }, [boardId, enabled, selection.kind, selection.id]);
  return rosterRef.current;
}

/**
 * Real-time collaboration via BoardActivity polling with reconnect/replay:
 * every `intervalMs` we fetch activity after the last seen id. If new committed
 * activity exists (another officer edited the board), we replay it by
 * invalidating the board query so the canvas re-syncs. This is the correctness
 * path (WebSocket/SSE is an optional deployed transport; see the phase report).
 */
export function useBoardActivityPoll(
  boardId: number | null,
  detail: BoardDetail | undefined,
  { enabled = true, intervalMs = 4000 }: { enabled?: boolean; intervalMs?: number } = {},
) {
  const qc = useQueryClient();
  const lastSeen = useRef<number>(0);
  const newestNotice = useRef<{ actor: string; action: string } | null>(null);

  // Route transitions reuse the workspace component. Reset the poll cursor and
  // transient notice so a freshly branched/opened board never inherits the
  // previous board's "locked" or activity message.
  useEffect(() => {
    lastSeen.current = 0;
    newestNotice.current = null;
  }, [boardId]);

  useEffect(() => {
    if (detail) lastSeen.current = Math.max(lastSeen.current, detail.latest_activity_id);
  }, [detail]);

  useEffect(() => {
    if (!boardId || !enabled) return;
    let alive = true;
    const tick = async () => {
      try {
        const res = await api.board.activity(boardId, lastSeen.current);
        if (!alive) return;
        if (res.count > 0) {
          const last = res.items[res.items.length - 1];
          lastSeen.current = res.latest_activity_id;
          newestNotice.current = { actor: last.actor, action: last.action };
          qc.invalidateQueries({ queryKey: boardKeys.detail(boardId) });
        }
      } catch {
        /* transient — retry next tick (reconnect uses the same after_id) */
      }
    };
    const h = window.setInterval(tick, intervalMs);
    return () => {
      alive = false;
      window.clearInterval(h);
    };
  }, [boardId, enabled, intervalMs, qc]);

  return { lastSeen, newestNotice };
}
