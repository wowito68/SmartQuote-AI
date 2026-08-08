export type UUID = string;

export type TenderStatus =
  | "draft"
  | "documents_pending"
  | "documents_processing"
  | "catalog_review"
  | "supplier_review"
  | "rfq_ready"
  | "waiting_quotes"
  | "closed"
  | "cancelled"
  | string;

export type Tender = {
  id: UUID;
  title: string;
  description: string | null;
  status: TenderStatus;
  deadline: string | null;
  created_by_user_id: UUID;
  created_at: string;
  updated_at: string;
};

export type TenderListResponse = {
  items: Tender[];
  total: number;
};

export type TenderDocument = {
  id: UUID;
  tender_id: UUID;
  original_file_name: string;
  mime_type: string;
  file_size: number;
  file_hash: string;
  status: string;
  uploaded_by_user_id: UUID;
  uploaded_at: string;
  updated_at: string;
};

export type DocumentListResponse = {
  items: TenderDocument[];
  total: number;
};

export type DocumentStatus = {
  document_id: UUID;
  status: string;
  extraction_status?: string | null;
  quality_status?: string | null;
  pages_total?: number;
  latest_error?: string | null;
};

export type CatalogProduct = {
  id: UUID;
  tender_id: UUID;
  source_document_id: UUID;
  item_number: string | null;
  name: string;
  description: string | null;
  quantity: string | number | null;
  unit: string | null;
  category: string | null;
  specifications: Record<string, string>;
  observations: string | null;
  confidence: number;
  status: string;
  reviewed_by_user_id: UUID | null;
  reviewed_at: string | null;
  rejection_reason: string | null;
};

export type CatalogMetrics = {
  products_total: number;
  products_pending_review: number;
  products_approved: number;
  products_rejected: number;
  average_confidence: number;
  manual_edit_percentage: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: string | number;
};

export type TenderCatalog = {
  tender_id: UUID;
  products: CatalogProduct[];
  metrics: CatalogMetrics;
  latest_snapshot_id: UUID | null;
  latest_snapshot_version: number | null;
};

export type SupplierContact = {
  id: UUID;
  contact_type: string;
  value: string;
  confidence: number;
  source_url: string;
  contact_name: string | null;
  role: string | null;
};

export type SupplierSource = {
  id: UUID;
  provider_name: string;
  source_type: string;
  source_url: string;
  source_title: string | null;
  excerpt: string | null;
  discovery_run_id?: UUID | null;
  product_id?: UUID | null;
  query?: string | null;
  source_name?: string | null;
  metadata?: Record<string, unknown>;
  discovered_at: string;
};

export type SupplierMatch = {
  product_id: UUID;
  score: number;
  reasons: string[];
  match_status?: string;
  source_url?: string | null;
  reason?: string | null;
};

export type TenderSupplier = {
  id: UUID;
  tender_id: UUID;
  supplier_id: UUID;
  status: string;
  is_manual: boolean;
  legal_name: string | null;
  trade_name: string | null;
  website: string | null;
  normalized_domain?: string | null;
  category: string | null;
  country: string | null;
  city: string | null;
  description: string | null;
  rejection_reason: string | null;
  contacts: SupplierContact[];
  sources: SupplierSource[];
  matches: SupplierMatch[];
  created_at: string;
  updated_at: string;
};

export type SupplierMetrics = {
  suppliers_total: number;
  suppliers_pending_review: number;
  suppliers_approved: number;
  suppliers_rejected: number;
  suppliers_merged: number;
  duplicates_detected: number;
  suppliers_with_valid_contact: number;
  valid_contact_percentage: number;
  approval_percentage: number;
};

export type TenderSuppliers = {
  tender_id: UUID;
  suppliers: TenderSupplier[];
  metrics: SupplierMetrics;
};

export type Rfq = {
  id: UUID;
  tender_id: UUID;
  tender_supplier_id: UUID;
  supplier_id: UUID;
  status: string;
  version: number;
  subject: string;
  body: string;
  to_recipients: string[];
  cc_recipients: string[];
  bcc_recipients: string[];
  response_deadline: string;
  observations: string | null;
  approved_at: string | null;
  queued_at: string | null;
  sent_at: string | null;
  last_error: string | null;
  attachments: Array<{
    id: UUID;
    document_id: UUID;
    original_file_name: string;
    file_hash: string;
    file_size: number;
    mime_type: string;
  }>;
  created_at: string;
  updated_at: string;
};

export type RfqMetrics = {
  total: number;
  pending_review: number;
  approved: number;
  queued: number;
  sent: number;
  failed: number;
  cancelled: number;
  success_percentage: number;
};

export type TenderRfqs = {
  tender_id: UUID;
  rfqs: Rfq[];
  metrics: RfqMetrics;
};
