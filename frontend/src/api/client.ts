// All HTTP traffic to the backend goes through this module — no other file
// in the project should call `fetch` directly.
//
// Identity (ADR 016): the user's corporate email is stored in localStorage
// and forwarded on every request as `X-Session-Token`. The frontend has no
// real authentication; the deployment context (corporate intranet, behind
// the IdP perimeter) is what makes that safe. See `docs/SPEC.md` §0.

import type {
  AnalyticsResponse,
  ClientSummary,
  PositionResponse,
  RejectedRowsResponse,
  UploadHistoryItem,
  UploadResponse,
  ViolationResponse,
} from "../types";

const EMAIL_STORAGE_KEY = "lumina:user-email";
const API_BASE = "/api/v1";

// ── identity helpers ─────────────────────────────────────────────────────────

export function getStoredEmail(): string | null {
  return localStorage.getItem(EMAIL_STORAGE_KEY);
}

export function setStoredEmail(email: string): void {
  localStorage.setItem(EMAIL_STORAGE_KEY, email);
}

export function clearStoredEmail(): void {
  localStorage.removeItem(EMAIL_STORAGE_KEY);
}

// ── HTTP wrapper ─────────────────────────────────────────────────────────────

export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;
  constructor(status: number, body: unknown, message: string) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

/**
 * 422 from POST /upload-transactions carries a `rejected_rows` payload.
 * Callers narrow with `isRejectedRows` and render the row-level errors.
 */
export function isRejectedRows(body: unknown): body is RejectedRowsResponse {
  return (
    typeof body === "object" &&
    body !== null &&
    Array.isArray((body as RejectedRowsResponse).rejected_rows)
  );
}

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const email = getStoredEmail();
  const headers = new Headers(init.headers);
  if (email) {
    headers.set("X-Session-Token", email);
  }
  // Don't override Content-Type when the caller passed FormData — the browser
  // needs to set its own multipart boundary.
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  const text = await response.text();
  const body: unknown = text ? safeJson(text) : null;

  if (!response.ok) {
    const message = extractMessage(body) ?? `${response.status} ${response.statusText}`;
    throw new ApiError(response.status, body, message);
  }
  return body as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function extractMessage(body: unknown): string | null {
  if (typeof body === "object" && body !== null && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
  }
  return null;
}

// ── endpoint functions ──────────────────────────────────────────────────────

export async function uploadTransactions(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  return request<UploadResponse>("/upload-transactions", {
    method: "POST",
    body: form,
  });
}

export async function listClients(): Promise<ClientSummary[]> {
  return request<ClientSummary[]>("/clients");
}

export async function getClientPositions(
  clientId: string,
): Promise<PositionResponse[]> {
  return request<PositionResponse[]>(
    `/clients/${encodeURIComponent(clientId)}/positions`,
  );
}

export async function listViolations(
  filters: { client_id?: string; violation_type?: string } = {},
): Promise<ViolationResponse[]> {
  const params = new URLSearchParams();
  if (filters.client_id) params.set("client_id", filters.client_id);
  if (filters.violation_type) params.set("violation_type", filters.violation_type);
  const query = params.toString();
  return request<ViolationResponse[]>(`/violations${query ? `?${query}` : ""}`);
}

export async function getAnalytics(): Promise<AnalyticsResponse> {
  return request<AnalyticsResponse>("/analytics");
}

export async function listUploads(): Promise<UploadHistoryItem[]> {
  return request<UploadHistoryItem[]>("/uploads");
}

export async function setLastViewedUpload(
  uploadId: number,
): Promise<UploadResponse> {
  return request<UploadResponse>("/users/me/last-viewed", {
    method: "PUT",
    body: JSON.stringify({ upload_id: uploadId }),
  });
}
