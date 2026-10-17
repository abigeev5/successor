import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  api,
  ApiError,
  toApiError,
  unwrap,
  type CandidateDecision,
  type ProcessCoverage,
  type Session,
  type SessionBrief,
} from "./client";

export function useCoverage(handoverId: string | undefined) {
  return useQuery<ProcessCoverage[]>({
    queryKey: ["coverage", handoverId],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/interviews/coverage", {
          params: { query: { handover_id: handoverId! } },
        }),
      ),
    enabled: !!handoverId,
  });
}

export function useSessions(handoverId: string | undefined, enabled = true) {
  return useQuery<SessionBrief[]>({
    queryKey: ["sessions", handoverId],
    queryFn: async () =>
      unwrap(await api.GET("/api/interviews", { params: { query: { handover_id: handoverId! } } })),
    enabled: !!handoverId && enabled,
  });
}

export function useStartInterview() {
  const queryClient = useQueryClient();
  return useMutation<Session, ApiError, string>({
    mutationFn: async (handoverId) =>
      unwrap(await api.POST("/api/interviews", { body: { handover_id: handoverId } })),
    onSuccess: (session) => queryClient.setQueryData(["session", session.id], session),
  });
}

export function useSession(id: string | undefined) {
  return useQuery<Session>({
    queryKey: ["session", id],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/interviews/{session_id}", { params: { path: { session_id: id! } } }),
      ),
    enabled: !!id,
  });
}

/** All session actions return the whole session; the cache is replaced with it. */
function useSessionAction<TVars>(id: string, call: (vars: TVars) => Promise<Session>) {
  const queryClient = useQueryClient();
  return useMutation<Session, ApiError, TVars>({
    mutationFn: call,
    onSuccess: (session) => {
      queryClient.setQueryData(["session", id], session);
      queryClient.invalidateQueries({ queryKey: ["coverage", session.handover_id] });
      queryClient.invalidateQueries({ queryKey: ["sessions", session.handover_id] });
    },
  });
}

const path = (id: string) => ({ params: { path: { session_id: id } } });

export function useSessionActions(id: string) {
  return {
    send: useSessionAction(id, async (body: { text: string; audio_asset_id?: string | null }) =>
      unwrap(await api.POST("/api/interviews/{session_id}/messages", { ...path(id), body })),
    ),
    confirm: useSessionAction(id, async (items: CandidateDecision[]) =>
      unwrap(
        await api.POST("/api/interviews/{session_id}/confirm-processes", {
          ...path(id),
          body: { items },
        }),
      ),
    ),
    nextProcess: useSessionAction(id, async () =>
      unwrap(await api.POST("/api/interviews/{session_id}/next-process", path(id))),
    ),
    pause: useSessionAction(id, async () =>
      unwrap(await api.POST("/api/interviews/{session_id}/pause", path(id))),
    ),
    resume: useSessionAction(id, async () =>
      unwrap(await api.POST("/api/interviews/{session_id}/resume", path(id))),
    ),
    finish: useSessionAction(id, async () =>
      unwrap(await api.POST("/api/interviews/{session_id}/finish", path(id))),
    ),
  };
}

export type Recognized = { asset_id: string; text: string; duration_ms: number | null };

/** Multipart upload goes through plain fetch: openapi-fetch does not build FormData bodies. */
export async function uploadAudio(sessionId: string, audio: Blob): Promise<Recognized> {
  const form = new FormData();
  form.append("file", audio, "answer.webm");
  const response = await fetch(`/api/interviews/${sessionId}/audio`, {
    method: "POST",
    body: form,
    credentials: "same-origin",
  });
  const body = await response.json().catch(() => undefined);
  if (!response.ok) throw toApiError(response.status, body);
  return body as Recognized;
}
