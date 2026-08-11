import type { UUID } from "../../lib/types";

export type ComparisonWarning = {
  code: string;
  severity: "warning" | "critical";
  message: string;
  supplier_id: UUID | null;
  quote_id: UUID | null;
  quote_item_id: UUID | null;
};

export type ComparisonOffer = {
  id: UUID;
  supplier_id: UUID;
  supplier_name: string;
  status: "quoted" | "missing" | "invalid";
  quote_id: UUID | null;
  quote_item_id: UUID | null;
  quoted_product_name: string | null;
  brand: string | null;
  model: string | null;
  quantity: string | number | null;
  unit: string | null;
  quantity_status: "matched" | "quantity_mismatch" | "unit_mismatch" | "unknown";
  unit_price: string | number | null;
  total_price: string | number | null;
  currency: string | null;
  compliance: "compliant" | "partially_compliant" | "non_compliant" | "unknown";
  delivery_days: number | null;
  delivery_original_text: string | null;
  delivery_normalized: boolean;
  observations: string | null;
  commercial_terms: string | null;
  evidence_id: UUID | null;
  confidence: number | null;
  warnings: ComparisonWarning[];
};

export type ComparisonItem = {
  id: UUID;
  product_id: UUID;
  requested_product: string;
  requested_quantity: string | number | null;
  requested_unit: string | null;
  monetary_status: "comparable" | "requires_normalization" | "insufficient_data";
  offers: ComparisonOffer[];
  warnings: ComparisonWarning[];
};

export type Comparison = {
  id: UUID;
  tender_id: UUID;
  catalog_snapshot_id: UUID;
  catalog_version: number;
  quotes_version: string;
  comparison_version: string;
  comparison_key: string;
  status: "draft" | "building" | "ready" | "invalid" | "archived";
  created_by_user_id: UUID;
  source_quote_ids: UUID[];
  items: ComparisonItem[];
  warnings: ComparisonWarning[];
  created_at: string;
  completed_at: string | null;
};
