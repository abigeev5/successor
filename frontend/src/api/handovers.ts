import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  api,
  ApiError,
  unwrap,
  type Consent,
  type ConsentText,
  type Handover,
  type HandoverCreate,
  type Process,
  type ProcessFrequency,
  type UserBrief,
  type UserRole,
} from "./client";

export function useHandovers() {
  return useQuery<Handover[]>({
    queryKey: ["handovers"],
    queryFn: async () => unwrap(await api.GET("/api/handovers")),
  });
}

export function useHandover(id: string | undefined) {
  return useQuery<Handover>({
    queryKey: ["handovers", id],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/handovers/{handover_id}", { params: { path: { handover_id: id! } } }),
      ),
    enabled: !!id,
  });
}

export function useCreateHandover() {
  const queryClient = useQueryClient();
  return useMutation<Handover, ApiError, HandoverCreate>({
    mutationFn: async (body) => unwrap(await api.POST("/api/handovers", { body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["handovers"] }),
  });
}

export function useProcesses(enabled = true) {
  return useQuery<Process[]>({
    queryKey: ["processes"],
    queryFn: async () => unwrap(await api.GET("/api/processes")),
    enabled,
  });
}

export function useCreateProcess() {
  const queryClient = useQueryClient();
  return useMutation<
    Process,
    ApiError,
    { name: string; criticality: number; frequency: ProcessFrequency }
  >({
    mutationFn: async (body) =>
      unwrap(await api.POST("/api/processes", { body: { ...body, description: "" } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["processes"] }),
  });
}

export function useUsers(role: UserRole, enabled = true) {
  return useQuery<UserBrief[]>({
    queryKey: ["users", role],
    queryFn: async () => unwrap(await api.GET("/api/users", { params: { query: { role } } })),
    enabled,
  });
}

export function useConsentText() {
  return useQuery<ConsentText>({
    queryKey: ["consent-text"],
    queryFn: async () => unwrap(await api.GET("/api/consents/current-text")),
    staleTime: Infinity,
  });
}

export function useMyConsent(handoverId: string | undefined) {
  return useQuery<Consent | null>({
    queryKey: ["consent", handoverId],
    queryFn: async () => {
      const result = await api.GET("/api/consents/my", {
        params: { query: { handover_id: handoverId! } },
      });
      if (!result.response.ok) unwrap(result); // throws ApiError
      return result.data ?? null;
    },
    enabled: !!handoverId,
  });
}

export function useAcceptConsent(handoverId: string) {
  const queryClient = useQueryClient();
  return useMutation<Consent, ApiError>({
    mutationFn: async () =>
      unwrap(await api.POST("/api/consents", { body: { handover_id: handoverId } })),
    onSuccess: (consent) => queryClient.setQueryData(["consent", handoverId], consent),
  });
}
