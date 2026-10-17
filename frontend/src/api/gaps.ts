import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, unwrap, type Gap, type GapStatus, type Recognized } from "./client";
import { postAudio } from "./interviews";

export function useGaps(handoverId: string | undefined, status?: GapStatus) {
  return useQuery<Gap[]>({
    queryKey: ["gaps", handoverId, status ?? "all"],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/gaps", { params: { query: { handover_id: handoverId!, status } } }),
      ),
    enabled: !!handoverId,
  });
}

function useGapMutation<TVars>(call: (vars: TVars) => Promise<Gap>) {
  const queryClient = useQueryClient();
  return useMutation<Gap, ApiError, TVars>({
    mutationFn: call,
    onSuccess: (gap) => {
      queryClient.invalidateQueries({ queryKey: ["gaps", gap.handover_id] });
      queryClient.invalidateQueries({ queryKey: ["cards", gap.handover_id] });
    },
  });
}

const path = (id: string) => ({ params: { path: { gap_id: id } } });

export function useGapActions() {
  return {
    create: useGapMutation(
      async (v: { handoverId: string; question: string; qaId?: string | null }) =>
        unwrap(
          await api.POST("/api/gaps", {
            body: { handover_id: v.handoverId, question: v.question, qa_log_id: v.qaId ?? null },
          }),
        ),
    ),
    answer: useGapMutation(async (v: { id: string; text: string }) =>
      unwrap(
        await api.POST("/api/gaps/{gap_id}/answer", { ...path(v.id), body: { text: v.text } }),
      ),
    ),
    dismiss: useGapMutation(async (id: string) =>
      unwrap(await api.POST("/api/gaps/{gap_id}/dismiss", path(id))),
    ),
    reassign: useGapMutation(async (v: { id: string; assigneeId: string }) =>
      unwrap(
        await api.PATCH("/api/gaps/{gap_id}", {
          ...path(v.id),
          body: { assignee_id: v.assigneeId },
        }),
      ),
    ),
  };
}

export function uploadGapAudio(gapId: string, audio: Blob): Promise<Recognized> {
  return postAudio(`/api/gaps/${gapId}/audio`, audio);
}
