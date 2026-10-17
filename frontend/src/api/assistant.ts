import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, unwrap, type Answer } from "./client";

export function useHistory(handoverId: string) {
  return useQuery<Answer[]>({
    queryKey: ["assistant-history", handoverId],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/assistant/history", { params: { query: { handover_id: handoverId } } }),
      ),
  });
}

/** Appends the new answer to the cached history; a refusal also creates a gap. */
export function useAsk(handoverId: string) {
  const queryClient = useQueryClient();
  return useMutation<Answer, ApiError, string>({
    mutationFn: async (question) =>
      unwrap(await api.POST("/api/assistant/ask", { body: { handover_id: handoverId, question } })),
    onSuccess: (answer) => {
      queryClient.setQueryData<Answer[]>(["assistant-history", handoverId], (old) => [
        ...(old ?? []),
        answer,
      ]);
      if (answer.status === "refused") {
        queryClient.invalidateQueries({ queryKey: ["gaps", handoverId] });
      }
    },
  });
}

export function useFeedback(handoverId: string) {
  const queryClient = useQueryClient();
  return useMutation<Answer, ApiError, { qaId: string; helpful: boolean; comment?: string }>({
    mutationFn: async ({ qaId, helpful, comment }) =>
      unwrap(
        await api.POST("/api/assistant/{qa_id}/feedback", {
          params: { path: { qa_id: qaId } },
          body: { helpful, comment: comment || null },
        }),
      ),
    onSuccess: (answer) => {
      queryClient.setQueryData<Answer[]>(["assistant-history", handoverId], (old) =>
        (old ?? []).map((a) =>
          a.qa_id === answer.qa_id ? { ...answer, forwarded_to: a.forwarded_to } : a,
        ),
      );
    },
  });
}
