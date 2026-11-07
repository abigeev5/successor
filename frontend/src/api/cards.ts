import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  api,
  ApiError,
  unwrap,
  type CardDetail,
  type CardEdit,
  type CardListItem,
  type CardStatus,
} from "./client";

export function useCards(handoverId: string | undefined, status?: CardStatus) {
  return useQuery<CardListItem[]>({
    queryKey: ["cards", handoverId, status ?? "all"],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/cards", { params: { query: { handover_id: handoverId!, status } } }),
      ),
    enabled: !!handoverId,
  });
}

export function useCard(id: string | undefined) {
  return useQuery<CardDetail>({
    queryKey: ["card", id],
    queryFn: async () =>
      unwrap(await api.GET("/api/cards/{card_id}", { params: { path: { card_id: id! } } })),
    enabled: !!id,
  });
}

function useCardAction<TVars>(call: (vars: TVars) => Promise<CardDetail>) {
  const queryClient = useQueryClient();
  return useMutation<CardDetail, ApiError, TVars>({
    mutationFn: call,
    onSuccess: (card) => {
      queryClient.setQueryData(["card", card.id], card);
      queryClient.invalidateQueries({ queryKey: ["cards", card.handover_id] });
    },
  });
}

const path = (id: string) => ({ params: { path: { card_id: id } } });

export function useCardActions() {
  return {
    approve: useCardAction(
      async (v: { id: string; edits: CardEdit | null; review_seconds: number }) =>
        unwrap(
          await api.POST("/api/cards/{card_id}/approve", {
            ...path(v.id),
            body: { edits: v.edits, review_seconds: v.review_seconds },
          }),
        ),
    ),
    reject: useCardAction(
      async (v: { id: string; reason: string | null; review_seconds: number }) =>
        unwrap(
          await api.POST("/api/cards/{card_id}/reject", {
            ...path(v.id),
            body: { reason: v.reason, review_seconds: v.review_seconds },
          }),
        ),
    ),
    merge: useCardAction(async (v: { id: string; into: string }) =>
      unwrap(
        await api.POST("/api/cards/{card_id}/merge", {
          ...path(v.id),
          body: { into_card_id: v.into },
        }),
      ),
    ),
    edit: useCardAction(async (v: { id: string; edits: CardEdit }) =>
      unwrap(await api.PATCH("/api/cards/{card_id}", { ...path(v.id), body: v.edits })),
    ),
  };
}
