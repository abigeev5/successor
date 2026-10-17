import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

type Schemas = components["schemas"];
export type User = Schemas["UserOut"];
export type UserRole = User["role"];
export type UserBrief = Schemas["UserBrief"];
export type Meta = Schemas["MetaOut"];
export type Handover = Schemas["HandoverOut"];
export type HandoverCreate = Schemas["HandoverCreate"];
export type HandoverReason = Schemas["HandoverReason"];
export type Process = Schemas["ProcessOut"];
export type ProcessFrequency = Schemas["ProcessFrequency"];
export type Session = Schemas["SessionOut"];
export type SessionBrief = Schemas["SessionBrief"];
export type Message = Schemas["MessageOut"];
export type ProcessCoverage = Schemas["ProcessCoverageOut"];
export type Candidate = Schemas["ProcessCandidate"];
export type CandidateDecision = Schemas["CandidateDecision"];
export type CardListItem = Schemas["CardListItem"];
export type CardDetail = Schemas["CardDetail"];
export type CardEdit = Schemas["CardEdit"];
export type CardType = Schemas["CardType"];
export type CardStatus = Schemas["CardStatus"];
export type Source = Schemas["SourceOut"];
export type Consent = Schemas["ConsentOut"];
export type Answer = Schemas["AnswerOut"];
export type AnswerSource = Schemas["SourceRef"];
export type Verification = Answer["verification"];
export type Gap = Schemas["GapOut"];
export type GapStatus = Schemas["GapStatus"];
export type Recognized = Schemas["AudioOut"];
export type Recording = Schemas["RecordingOut"];
export type RecordingBrief = Schemas["RecordingBrief"];
export type RecordingStatus = Schemas["RecordingStatus"];
export type RecordingStage = Schemas["RecordingStage"];
export type RecordingStep = Schemas["StepOut"];
export type ConsentText = Schemas["ConsentTextOut"];
export type RiskMap = Schemas["RiskMapOut"];
export type ProcessRisk = Schemas["ProcessRiskOut"];
export type RiskLevel = Schemas["RiskLevel"];
export type AspectCell = Schemas["AspectCellOut"];
export type HandoverProgress = Schemas["HandoverProgressOut"];
export type Metrics = Schemas["MetricsOut"];
export type AuditEntry = Schemas["AuditEntryOut"];
export type MyData = Schemas["MyDataOut"];
export type Erased = Schemas["ErasedOut"];

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
