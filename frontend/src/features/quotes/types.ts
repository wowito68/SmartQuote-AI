import type { UUID } from "../../lib/types";

export type QuoteEvidence = {
  id: UUID;
  quote_item_id: UUID | null;
  quote_document_id: UUID;
  extraction_run_id: UUID;
  field_name: string;
  location_type: string;
  location_label: string;
  fragment: string;
  method: string;
  confidence: number;
  created_at: string;
};

export type QuoteDocument = {
  id: UUID;
  quote_id: UUID;
  original_file_name: string;
  mime_type: string;
  document_type: string;
  processing_status: string;
  file_hash: string;
  file_size: number;
  extractor_name: string | null;
  extractor_version: string | null;
  created_at: string;
};

export type QuoteItem = {
  id: UUID;
  catalog_product_id: UUID | null;
  product_name: string;
  description: string | null;
  brand: string | null;
  model: string | null;
  unit: string | null;
  quantity: string | number | null;
  unit_price: string | number | null;
  total_price: string | number | null;
  currency: string | null;
  delivery_days: number | null;
  compliance_status: string;
  match_status: string;
  match_score: number;
  match_reason: string | null;
  quoted_specifications: Record<string, string>;
  notes: string | null;
  confidence: number;
  confidence_band: string;
  warnings: string[];
  evidence: QuoteEvidence[];
  original_extracted: Record<string, unknown>;
};

export type QuoteDetail = {
  id: UUID;
  tender_id: UUID;
  tender_supplier_id: UUID;
  supplier_id: UUID;
  rfq_request_id: UUID | null;
  status: string;
  currency: string | null;
  subtotal_amount: string | number | null;
  tax_amount: string | number | null;
  total_amount: string | number | null;
  delivery_time_days: number | null;
  commercial_terms: string | null;
  valid_until: string | null;
  received_at: string;
  approved_extraction_run_id: UUID | null;
  version: number;
  manual_edit_count: number;
  reviewed_by_user_id: UUID | null;
  reviewed_at: string | null;
  rejection_reason: string | null;
  last_error: string | null;
  documents: QuoteDocument[];
  items: QuoteItem[];
  created_at: string;
  updated_at: string;
};

export type QuoteSummary = {
  id: UUID;
  tender_id: UUID;
  tender_supplier_id: UUID;
  supplier_id: UUID;
  original_file_name: string;
  status: string;
  created_at: string;
  updated_at: string;
};

export type ProcessingStatus = {
  quote_id: UUID;
  quote_status: string;
  correlation_id: string | null;
  task_status: string | null;
  attempt_count: number;
  extraction_runs: Array<{
    id: UUID;
    status: string;
    provider: string;
    model: string;
    prompt_version: string;
    schema_version: string;
    extractor_version: string;
    input_tokens: number;
    output_tokens: number;
    estimated_cost_usd: string;
    started_at: string | null;
    completed_at: string | null;
    error: string | null;
  }>;
  last_error: string | null;
};
