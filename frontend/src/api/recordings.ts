import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, toApiError, unwrap, type Recording, type RecordingBrief } from "./client";

const BUSY = new Set(["uploaded", "processing"]);
const POLL_MS = 2000;

export function useRecordings(handoverId: string | undefined, enabled = true) {
  return useQuery<RecordingBrief[]>({
    queryKey: ["recordings", handoverId],
    queryFn: async () =>
      unwrap(await api.GET("/api/recordings", { params: { query: { handover_id: handoverId! } } })),
    enabled: !!handoverId && enabled,
    refetchInterval: (query) =>
      query.state.data?.some((r) => BUSY.has(r.status)) ? POLL_MS : false,
  });
}

/** Polls while the worker processes the recording. */
export function useRecording(id: string | undefined) {
  return useQuery<Recording>({
    queryKey: ["recording", id],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/recordings/{recording_id}", {
          params: { path: { recording_id: id! } },
        }),
      ),
    enabled: !!id,
    refetchInterval: (query) =>
      query.state.data && BUSY.has(query.state.data.status) ? POLL_MS : false,
  });
}

export function useRetryRecording() {
  const queryClient = useQueryClient();
  return useMutation<Recording, ApiError, string>({
    mutationFn: async (id) =>
      unwrap(
        await api.POST("/api/recordings/{recording_id}/retry", {
          params: { path: { recording_id: id } },
        }),
      ),
    onSuccess: (recording) => queryClient.setQueryData(["recording", recording.id], recording),
  });
}

export type UploadFields = { handoverId: string; title: string; processId: string; video: Blob };

/** XMLHttpRequest, not fetch: only it reports upload progress (SPEC 7.6: progress bar). */
export function uploadRecording(
  fields: UploadFields,
  onProgress: (share: number) => void,
): Promise<Recording> {
  const form = new FormData();
  form.append("handover_id", fields.handoverId);
  form.append("title", fields.title);
  if (fields.processId) form.append("process_id", fields.processId);
  const name = fields.video instanceof File ? fields.video.name : "screen.webm";
  form.append("video", fields.video, name);
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/recordings");
    xhr.withCredentials = true;
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total);
    };
    xhr.onload = () => {
      let body: unknown;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        body = undefined;
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as Recording);
      else reject(toApiError(xhr.status, body as { detail?: unknown; code?: unknown }));
    };
    xhr.onerror = () =>
      reject(new ApiError(0, "network", "Связь прервалась. Попробуйте загрузить ещё раз."));
    xhr.send(form);
  });
}
