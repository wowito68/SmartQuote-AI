import { ApiError } from "../../lib/api";
import type { UUID } from "../../lib/types";
import type { Comparison } from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) {
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

export const comparisonApi = {
  latest: (tenderId: UUID) =>
    request<Comparison>(`/api/v1/tenders/${tenderId}/comparisons`),

  generate: (tenderId: UUID, userId: UUID) =>
    request<Comparison>(`/api/v1/tenders/${tenderId}/comparisons`, {
      method: "POST",
      body: JSON.stringify({ created_by_user_id: userId })
    }),

  get: (comparisonId: UUID) =>
    request<Comparison>(`/api/v1/comparisons/${comparisonId}`)
};
