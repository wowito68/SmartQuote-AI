import { ApiError } from "../../lib/api";
import type { UUID } from "../../lib/types";
import type { Quote, QuoteEvidence, TenderQuotes } from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  if (!response.ok) {
    const details = await response.json().catch(() => null);
    const message =
      details && typeof details === "object" && "message" in details
        ? String(details.message)
        : `Request failed with status ${response.status}`;
    throw new ApiError(message, response.status, details);
  }
  return response.json() as Promise<T>;
}

export const quoteApi = {
  list: (tenderId: UUID) => request<TenderQuotes>(`/api/v1/tenders/${tenderId}/quotes`),

  upload: (tenderId: UUID, userId: UUID, supplierId: UUID, rfqId: UUID | null, file: File) => {
    const form = new FormData();
    form.append("uploaded_by_user_id", userId);
    form.append("supplier_id", supplierId);
    if (rfqId) form.append("rfq_request_id", rfqId);
    form.append("files", file);
    return request<{ quote: Quote; duplicate_detected: boolean; queued: boolean }>(
      `/api/v1/tenders/${tenderId}/quotes`,
      { method: "POST", body: form }
    );
  },

  get: (quoteId: UUID) => request<Quote>(`/api/v1/quotes/${quoteId}`),

  evidence: (quoteId: UUID) =>
    request<{ items: QuoteEvidence[]; total: number }>(`/api/v1/quotes/${quoteId}/evidence`),

  process: (quoteId: UUID, userId: UUID) =>
    request(`/api/v1/quotes/${quoteId}/process`, {
      method: "POST",
      body: JSON.stringify({ requested_by_user_id: userId })
    }),

  reprocess: (quoteId: UUID, userId: UUID) =>
    request(`/api/v1/quotes/${quoteId}/reprocess`, {
      method: "POST",
      body: JSON.stringify({ requested_by_user_id: userId })
    }),

  updateItem: (quoteId: UUID, itemId: UUID, payload: Record<string, unknown>) =>
    request<Quote>(`/api/v1/quotes/${quoteId}/items/${itemId}`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),

  submitReview: (quoteId: UUID, userId: UUID) =>
    request<Quote>(`/api/v1/quotes/${quoteId}/submit-review`, {
      method: "POST",
      body: JSON.stringify({ reviewer_user_id: userId })
    }),

  approve: (quoteId: UUID, userId: UUID) =>
    request<Quote>(`/api/v1/quotes/${quoteId}/approve`, {
      method: "POST",
      body: JSON.stringify({ reviewer_user_id: userId })
    }),

  reject: (quoteId: UUID, userId: UUID, reason: string) =>
    request<Quote>(`/api/v1/quotes/${quoteId}/reject`, {
      method: "POST",
      body: JSON.stringify({ reviewer_user_id: userId, reason })
    })
};
