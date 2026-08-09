import type {
  DocumentListResponse,
  DocumentStatus,
  Rfq,
  RfqMessages,
  RfqVersions,
  Tender,
  TenderCatalog,
  TenderListResponse,
  TenderRfqs,
  TenderSupplier,
  TenderSuppliers,
  UUID
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export class ApiError extends Error {
  readonly status: number;
  readonly details: unknown;

  constructor(message: string, status: number, details: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers
  });

  if (!response.ok) {
    const details = await response.json().catch(() => null);
    const message =
      details && typeof details === "object" && "message" in details
        ? String(details.message)
        : `Request failed with status ${response.status}`;
    throw new ApiError(message, response.status, details);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export const api = {
  health: () =>
    request<{ status: string; project_name: string; version: string; environment: string }>(
      "/health"
    ),

  listTenders: () => request<TenderListResponse>("/api/v1/tenders"),

  createTender: (payload: {
    title: string;
    description: string | null;
    deadline: string | null;
    created_by_user_id: UUID;
  }) =>
    request<Tender>("/api/v1/tenders", {
      method: "POST",
      body: JSON.stringify(payload)
    }),

  archiveTender: (tenderId: UUID) =>
    request<void>(`/api/v1/tenders/${tenderId}`, { method: "DELETE" }),

  listDocuments: (tenderId: UUID) =>
    request<DocumentListResponse>(`/api/v1/tenders/${tenderId}/documents`),

  uploadDocuments: (tenderId: UUID, userId: UUID, files: FileList | File[]) => {
    const form = new FormData();
    form.append("uploaded_by_user_id", userId);
    Array.from(files).forEach((file) => form.append("files", file));
    return request<DocumentListResponse>(`/api/v1/tenders/${tenderId}/documents`, {
      method: "POST",
      body: form
    });
  },

  getDocumentStatus: (documentId: UUID) =>
    request<DocumentStatus>(`/api/v1/documents/${documentId}/status`),

  deleteDocument: (documentId: UUID, userId: UUID) =>
    request<void>(`/api/v1/documents/${documentId}?deleted_by_user_id=${userId}`, {
      method: "DELETE"
    }),

  requestCatalogExtraction: (tenderId: UUID) =>
    request<{ queued: number; reused: number }>(`/api/v1/tenders/${tenderId}/catalog/extract`, {
      method: "POST"
    }),

  getCatalog: (tenderId: UUID) =>
    request<TenderCatalog>(`/api/v1/tenders/${tenderId}/catalog`),

  approveProduct: (productId: UUID, userId: UUID) =>
    request(`/api/v1/catalog/${productId}`, {
      method: "PUT",
      body: JSON.stringify({ action: "approve", reviewer_user_id: userId })
    }),

  rejectProduct: (productId: UUID, userId: UUID, reason: string) =>
    request(`/api/v1/catalog/${productId}`, {
      method: "PUT",
      body: JSON.stringify({
        action: "reject",
        reviewer_user_id: userId,
        rejection_reason: reason
      })
    }),

  approveCatalog: (tenderId: UUID, userId: UUID) =>
    request(`/api/v1/tenders/${tenderId}/catalog/approve`, {
      method: "POST",
      body: JSON.stringify({ approved_by_user_id: userId })
    }),

  discoverSuppliers: (tenderId: UUID, userId: UUID) =>
    request(`/api/v1/tenders/${tenderId}/suppliers/discover`, {
      method: "POST",
      body: JSON.stringify({ requested_by_user_id: userId })
    }),

  listSuppliers: (tenderId: UUID) =>
    request<TenderSuppliers>(`/api/v1/tenders/${tenderId}/suppliers`),

  createManualSupplier: (payload: {
    tender_id: UUID;
    created_by_user_id: UUID;
    legal_name: string | null;
    trade_name: string | null;
    website: string | null;
    category: string | null;
    country: string | null;
    city: string | null;
    description: string | null;
    contacts: Array<{
      contact_type: string;
      value: string;
      confidence: number;
      source_url: string;
      contact_name: string | null;
      role: string | null;
    }>;
    source_note: string | null;
  }) =>
    request<TenderSupplier>("/api/v1/suppliers/manual", {
      method: "POST",
      body: JSON.stringify(payload)
    }),

  approveSupplier: (supplierId: UUID, userId: UUID) =>
    request<TenderSupplier>(`/api/v1/suppliers/${supplierId}/approve`, {
      method: "POST",
      body: JSON.stringify({ reviewer_user_id: userId })
    }),

  rejectSupplier: (supplierId: UUID, userId: UUID, reason: string) =>
    request<TenderSupplier>(`/api/v1/suppliers/${supplierId}/reject`, {
      method: "POST",
      body: JSON.stringify({ reviewer_user_id: userId, reason })
    }),

  generateRfq: (
    tenderId: UUID,
    payload: {
      supplier_id: UUID;
      contact_id: UUID;
      product_ids: UUID[];
      document_ids: UUID[];
      generated_by_user_id: UUID;
      response_deadline: string;
      observations: string | null;
      requested_currency: string | null;
      commercial_terms: string | null;
      quote_validity: string | null;
      response_instructions: string | null;
    }
  ) =>
    request<Rfq>(`/api/v1/tenders/${tenderId}/rfqs`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),

  generateRfqs: (
    tenderId: UUID,
    payload: {
      generated_by_user_id: UUID;
      response_deadline: string;
      observations: string | null;
      document_ids: UUID[] | null;
    }
  ) =>
    request<{ generated: Rfq[]; reused: Rfq[]; suppliers_without_email: UUID[] }>(
      `/api/v1/tenders/${tenderId}/rfqs/generate`,
      {
        method: "POST",
        body: JSON.stringify(payload)
      }
    ),

  listRfqs: (tenderId: UUID) => request<TenderRfqs>(`/api/v1/tenders/${tenderId}/rfqs`),

  getRfq: (rfqId: UUID) => request<Rfq>(`/api/v1/rfqs/${rfqId}`),

  updateRfq: (
    rfqId: UUID,
    payload: {
      changed_by_user_id: UUID;
      subject?: string;
      body?: string;
      response_deadline?: string;
      observations?: string | null;
      document_ids?: UUID[];
      change_reason?: string | null;
    }
  ) =>
    request<Rfq>(`/api/v1/rfqs/${rfqId}`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),

  submitRfqReview: (rfqId: UUID, userId: UUID) =>
    request<Rfq>(`/api/v1/rfqs/${rfqId}/submit-review`, {
      method: "POST",
      body: JSON.stringify({ reviewed_by_user_id: userId })
    }),

  approveRfq: (rfqId: UUID, userId: UUID) =>
    request<Rfq>(`/api/v1/rfqs/${rfqId}/approve`, {
      method: "POST",
      body: JSON.stringify({ approved_by_user_id: userId })
    }),

  rejectRfq: (rfqId: UUID, userId: UUID, reason: string) =>
    request<Rfq>(`/api/v1/rfqs/${rfqId}/reject`, {
      method: "POST",
      body: JSON.stringify({ reviewed_by_user_id: userId, reason })
    }),

  sendRfq: (rfqId: UUID, userId: UUID) =>
    request<Rfq>(`/api/v1/rfqs/${rfqId}/send`, {
      method: "POST",
      body: JSON.stringify({ requested_by_user_id: userId })
    }),

  retryRfq: (rfqId: UUID, userId: UUID) =>
    request<Rfq>(`/api/v1/rfqs/${rfqId}/retry`, {
      method: "POST",
      body: JSON.stringify({ requested_by_user_id: userId })
    }),

  cancelRfq: (rfqId: UUID, userId: UUID, reason: string | null) =>
    request<Rfq>(`/api/v1/rfqs/${rfqId}/cancel`, {
      method: "POST",
      body: JSON.stringify({ cancelled_by_user_id: userId, reason })
    }),

  getRfqMessages: (rfqId: UUID) => request<RfqMessages>(`/api/v1/rfqs/${rfqId}/messages`),

  getRfqVersions: (rfqId: UUID) => request<RfqVersions>(`/api/v1/rfqs/${rfqId}/versions`)
};