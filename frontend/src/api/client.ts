import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

export type User = components["schemas"]["UserOut"];
export type UserRole = User["role"];
export type Meta = components["schemas"]["MetaOut"];

/**
 * Typed API client. Same origin: nginx (prod) or the Vite proxy (dev) forward /api to the backend.
 * An absolute baseUrl is required: openapi-fetch builds a Request, which rejects relative URLs.
 * `fetch` is looked up on each call so tests can stub it.
 */
export const api = createClient<paths>({
  baseUrl: globalThis.location?.origin ?? "",
  fetch: (request) => globalThis.fetch(request),
});

/** Backend error: {"detail": "<text in Russian>", "code": "..."}. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

type ErrorBody = { detail?: unknown; code?: unknown } | undefined;

export function toApiError(status: number, body: ErrorBody): ApiError {
  const detail =
    typeof body?.detail === "string" ? body.detail : "Что-то пошло не так. Попробуйте ещё раз.";
  const code = typeof body?.code === "string" ? body.code : "unknown";
  return new ApiError(status, code, detail);
}

/** Unwraps an openapi-fetch result: returns data or throws ApiError. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.error !== undefined || result.data === undefined) {
    throw toApiError(result.response.status, result.error as ErrorBody);
  }
  return result.data;
}
