import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, toApiError, unwrap, type Meta, type User } from "./client";

const ME = ["me"] as const;

/** Current user, or null when not logged in (401 is not an error here). */
export function useMe() {
  return useQuery<User | null>({
    queryKey: ME,
    queryFn: async () => {
      const result = await api.GET("/api/auth/me");
      if (result.response.status === 401) return null;
      return unwrap(result);
    },
    staleTime: 5 * 60_000,
  });
}

export function useMeta() {
  return useQuery<Meta>({
    queryKey: ["meta"],
    queryFn: async () => unwrap(await api.GET("/api/meta")),
    staleTime: Infinity,
  });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation<User, ApiError, { email: string; password: string }>({
    mutationFn: async (body) => unwrap(await api.POST("/api/auth/login", { body })),
    onSuccess: (user) => queryClient.setQueryData(ME, user),
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation<void, ApiError>({
    mutationFn: async () => {
      const { response } = await api.POST("/api/auth/logout");
      if (!response.ok) throw toApiError(response.status, undefined);
    },
    onSuccess: () => {
      queryClient.clear();
      queryClient.setQueryData(ME, null);
    },
  });
}
