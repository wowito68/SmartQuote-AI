import type { UUID } from "../../lib/types";

export type ComparisonStatus = "draft" | "building" | "ready" | "invalid" | "archived";
export type ComparisonWarningSeverity = "warning" | "critical";
export type ComparisonOfferStatus = "quoted" | "missing" | "invalid";
export type MonetaryComparisonStatus =
  | "comparable"
  | "requires_normalization"
  | "insufficient_data";
export type QuantityComparisonStatus =
  | "matched"
  | "quantity_mismatch"
  | "unit_mismatch"
  | "unknown";
export type ComparisonCompliance =
  | "compliant"
  | "partially_compliant"
  | "non_compliant"
  | "unknown";

export type ComparisonWarning = {
  code: string;
  severity: ComparisonWarningSeverity;
  message: string;
  supplier_id: UUID | null;
  quote_id: UUID | null;
  quote_item_id: UUID | null;
};

export type ComparisonOffer = {
  id: UUID;
  supplier_id: UUID;
  supplier_name: string;
  status: ComparisonOfferStatus;
  quote_id: UUID | null;
  quote_item_id: UUID | null;
  quoted_product_name: string | null;
  brand: string | null;
  model: string | null;
  quantity: string | number | null;
  unit: string | null;
  quantity_status: QuantityComparisonStatus;
  unit_price: string | number | null;
  total_price: string | number | null;
  currency: string | null;
  compliance: ComparisonCompliance;
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
  monetary_status: MonetaryComparisonStatus;
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
  status: ComparisonStatus;
  created_by_user_id: UUID;
  source_quote_ids: UUID[];
  items: ComparisonItem[];
  warnings: ComparisonWarning[];
  created_at: string;
  completed_at: string | null;
};

export type RecommendationStatus = "ready" | "withheld";

export type RecommendationWeights = {
  technical: string | number;
  price: string | number;
  delivery: string | number;
};

export type RecommendationCandidate = {
  supplier_id: UUID;
  supplier_name: string;
  eligible: boolean;
  product_count: number;
  technical_score: string | number | null;
  price_score: string | number | null;
  delivery_score: string | number | null;
  score: string | number | null;
  exclusion_reasons: string[];
};

export type Recommendation = {
  id: UUID;
  comparison_id: UUID;
  tender_id: UUID;
  recommendation_key: string;
  policy_version: string;
  weights: RecommendationWeights;
  generated_by_user_id: UUID;
  status: RecommendationStatus;
  candidates: RecommendationCandidate[];
  recommended_supplier_id: UUID | null;
  recommended_supplier_name: string | null;
  explanation: string;
  warnings: string[];
  human_review_required: boolean;
  created_at: string;
};
