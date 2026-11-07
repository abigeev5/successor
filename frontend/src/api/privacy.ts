import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, unwrap, type Consent, type Erased, type MyData } from "./client";

export function useMyData(handoverId: string | undefined) {
  return useQuery<MyData>({
    queryKey: ["my-data", handoverId],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/privacy/my-data", { params: { query: { handover_id: handoverId! } } }),
      ),
    enabled: !!handoverId,
  });
}

/** Deletion touches much of a handover: stored data, recordings, cards, sessions, consent. */
const AFFECTED = ["my-data", "recordings", "consent", "cards", "coverage", "sessions", "progress"];

function invalidateAffected(queryClient: ReturnType<typeof useQueryClient>) {
  for (const key of AFFECTED) void queryClient.invalidateQueries({ queryKey: [key] });
}

export function useEraseMyData(handoverId: string) {
  const queryClient = useQueryClient();
  return useMutation<Erased, ApiError>({
    mutationFn: async () =>
      unwrap(
        await api.DELETE("/api/privacy/my-data", {
          params: { query: { handover_id: handoverId } },
        }),
      ),
    onSuccess: () => invalidateAffected(queryClient),
  });
}

export function useRevokeConsent() {
  const queryClient = useQueryClient();
  return useMutation<Consent, ApiError, string>({
    mutationFn: async (consentId) =>
      unwrap(
        await api.POST("/api/consents/{consent_id}/revoke", {
          params: { path: { consent_id: consentId } },
        }),
      ),
    onSuccess: () => invalidateAffected(queryClient),
  });
}

export function useDeleteRecording() {
  const queryClient = useQueryClient();
  return useMutation<void, ApiError, string>({
    mutationFn: async (recordingId) => {
      const result = await api.DELETE("/api/recordings/{recording_id}", {
        params: { path: { recording_id: recordingId } },
      });
      if (!result.response.ok) unwrap(result); // throws ApiError
    },
    onSuccess: () => invalidateAffected(queryClient),
  });
}
