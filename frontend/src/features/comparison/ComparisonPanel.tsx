import { FileSearch, RefreshCcw } from "lucide-react";
import { useMemo } from "react";

import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  LoadingState,
  Section,
  StatusBadge
} from "../../components/ui";
import { formatDate } from "../../lib/format";
import type { UUID } from "../../lib/types";
import type {
  Comparison,
  ComparisonCompliance,
  ComparisonOffer,
  ComparisonWarning
} from "./types";

export function ComparisonPanel({
  tenderId,
  comparison,
  loading,
  generating,
  onRefresh,
  onGenerate
}: {
  tenderId: UUID | null;
  comparison: Comparison | null;
  loading: boolean;
  generating: boolean;
  onRefresh: () => Promise<void>;
  onGenerate: () => Promise<void>;
}) {
  const suppliers = useMemo(() => {
    const values = new Map<UUID, string>();
    comparison?.items.forEach((item) => {
      item.offers.forEach((offer) => values.set(offer.supplier_id, offer.supplier_name));
    });
    return [...values.entries()].map(([id, name]) => ({ id, name }));
  }, [comparison]);

  if (loading && !comparison) {
    return <LoadingState label="Cargando comparativo" />;
  }

  return (
    <Section
      title="Comparativo"
      eyebrow="Cierre del MVP"
      description="Compara las cotizaciones aprobadas sin ranking, conversion FX ni seleccion automatica de proveedor."
      action={
        <>
          <Button
            variant="secondary"
            disabled={!tenderId}
            onClick={() => void onRefresh()}
          >
            <RefreshCcw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            Refrescar
          </Button>
          <Button
            disabled={!tenderId}
            loading={generating}
            onClick={() => void onGenerate()}
          >
            Generar comparativo
          </Button>
        </>
      }
    >
      {!tenderId ? (
        <EmptyState
          title="Sin licitacion seleccionada"
          detail="Selecciona una licitacion para consultar o generar su comparativo."
        />
      ) : !comparison ? (
        <EmptyState
          icon={<FileSearch className="h-5 w-5" />}
          title="Aun no existe un comparativo"
          detail="El comparativo requiere un catalogo aprobado y al menos una cotizacion aprobada."
          action={
            <Button loading={generating} onClick={() => void onGenerate()}>
              Generar comparativo
            </Button>
          }
        />
      ) : (
        <div className="grid gap-5">
          <ComparisonSummary comparison={comparison} />
          {comparison.status === "invalid" ? (
            <Alert
              tone="danger"
              title="Comparativo invalido"
              detail="Existen inconsistencias criticas. Revisa las advertencias antes de usar este resultado."
            />
          ) : comparison.warnings.length > 0 ? (
            <Alert
              tone="warning"
              title="Comparativo con advertencias"
              detail="Las advertencias no criticas se conservan y no se interpretan como valores validos por defecto."
            />
          ) : null}
          <ComparisonWarnings warnings={comparison.warnings} />
          <ComparisonMatrix comparison={comparison} suppliers={suppliers} />
        </div>
      )}
    </Section>
  );
}

function ComparisonSummary({ comparison }: { comparison: Comparison }) {
  const warningCount =
    comparison.warnings.length +
    comparison.items.reduce(
      (total, item) =>
        total +
        item.warnings.length +
        item.offers.reduce((offerTotal, offer) => offerTotal + offer.warnings.length, 0),
      0
    );

  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
      <Metric label="Estado" value={<StatusBadge value={comparison.status} />} />
      <Metric label="Catalogo" value={`v${comparison.catalog_version}`} />
      <Metric label="Reglas" value={comparison.comparison_version} />
      <Metric label="Cotizaciones fuente" value={String(comparison.source_quote_ids.length)} />
      <Metric label="Advertencias" value={String(warningCount)} />
      <Card className="sm:col-span-2 xl:col-span-5" padding="sm">
        <div className="grid gap-1 text-xs text-text-secondary sm:grid-cols-2">
          <p>
            Generado: <span className="font-medium text-text-primary">{formatDate(comparison.created_at)}</span>
          </p>
          <p className="truncate font-mono" title={comparison.comparison_key}>
            Huella: {comparison.comparison_key}
          </p>
        </div>
      </Card>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <Card padding="sm">
      <p className="text-xs font-medium uppercase tracking-wide text-text-secondary">{label}</p>
      <div className="mt-2 text-lg font-semibold text-text-primary">{value}</div>
    </Card>
  );
}

function ComparisonWarnings({ warnings }: { warnings: ComparisonWarning[] }) {
  if (warnings.length === 0) return null;
  return (
    <Card padding="sm">
      <p className="text-sm font-semibold text-text-primary">Advertencias generales</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {warnings.map((warning, index) => (
          <Badge key={`${warning.code}-${index}`} tone={warning.severity === "critical" ? "danger" : "warning"}>
            {warning.code}
          </Badge>
        ))}
      </div>
    </Card>
  );
}

function ComparisonMatrix({
  comparison,
  suppliers
}: {
  comparison: Comparison;
  suppliers: Array<{ id: UUID; name: string }>;
}) {
  return (
    <Card padding="none" className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="min-w-full border-collapse text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-text-secondary">
            <tr>
              <th className="min-w-64 border-b border-border-subtle px-4 py-3">Producto solicitado</th>
              {suppliers.map((supplier) => (
                <th key={supplier.id} className="min-w-80 border-b border-l border-border-subtle px-4 py-3">
                  {supplier.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {comparison.items.map((item) => (
              <tr key={item.id} className="align-top">
                <td className="border-b border-border-subtle px-4 py-4">
                  <p className="font-semibold text-text-primary">{item.requested_product}</p>
                  <p className="mt-1 text-xs text-text-secondary">
                    Solicitado: {formatNumber(item.requested_quantity)} {item.requested_unit ?? "unidad desconocida"}
                  </p>
                  <div className="mt-3">
                    <Badge tone={item.monetary_status === "comparable" ? "success" : "warning"}>
                      {item.monetary_status}
                    </Badge>
                  </div>
                  <WarningBadges warnings={item.warnings} />
                </td>
                {suppliers.map((supplier) => {
                  const offer = item.offers.find((candidate) => candidate.supplier_id === supplier.id);
                  return (
                    <td key={supplier.id} className="border-b border-l border-border-subtle px-4 py-4">
                      {offer ? <OfferCell offer={offer} /> : <MissingOffer />}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function OfferCell({ offer }: { offer: ComparisonOffer }) {
  if (offer.status === "missing") return <MissingOffer />;
  const delivery = offer.delivery_days !== null
    ? `${offer.delivery_days} dias`
    : offer.delivery_original_text ?? "Desconocida";
  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge value={offer.status} />
        <Badge tone={complianceTone(offer.compliance)}>{offer.compliance}</Badge>
        {offer.confidence !== null ? (
          <Badge>{Math.round(offer.confidence * 100)}% confianza</Badge>
        ) : null}
      </div>
      <div>
        <p className="font-semibold text-text-primary">
          {offer.quoted_product_name ?? "Producto no identificado"}
        </p>
        <p className="mt-1 text-xs text-text-secondary">
          {[offer.brand, offer.model].filter(Boolean).join(" · ") || "Marca/modelo no indicado"}
        </p>
      </div>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
        <Data label="Cantidad" value={`${formatNumber(offer.quantity)} ${offer.unit ?? "—"}`} />
        <Data label="Cantidad vs solicitud" value={offer.quantity_status} />
        <Data label="Precio unitario" value={formatMoney(offer.unit_price, offer.currency)} />
        <Data label="Precio total" value={formatMoney(offer.total_price, offer.currency)} />
        <Data label="Entrega" value={delivery} />
        <Data label="Evidencia" value={offer.evidence_id ? "Disponible" : "No referenciada"} />
      </dl>
      {offer.commercial_terms ? (
        <p className="text-xs leading-5 text-text-secondary">
          <span className="font-medium text-text-primary">Condiciones:</span> {offer.commercial_terms}
        </p>
      ) : null}
      {offer.observations ? (
        <p className="text-xs leading-5 text-text-secondary">
          <span className="font-medium text-text-primary">Observaciones:</span> {offer.observations}
        </p>
      ) : null}
      <WarningBadges warnings={offer.warnings} />
    </div>
  );
}

function MissingOffer() {
  return (
    <div className="rounded-panel border border-dashed border-border-subtle bg-slate-50 p-4">
      <Badge tone="warning">No cotizado</Badge>
      <p className="mt-2 text-xs text-text-secondary">Sin QuoteItem. Precio y cantidad permanecen nulos.</p>
    </div>
  );
}

function WarningBadges({ warnings }: { warnings: ComparisonWarning[] }) {
  if (warnings.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {warnings.map((warning, index) => (
        <Badge key={`${warning.code}-${index}`} tone={warning.severity === "critical" ? "danger" : "warning"}>
          {warning.code}
        </Badge>
      ))}
    </div>
  );
}

function Data({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-text-secondary">{label}</dt>
      <dd className="mt-0.5 font-medium text-text-primary">{value}</dd>
    </div>
  );
}

function complianceTone(value: ComparisonCompliance): "success" | "warning" | "danger" | "neutral" {
  if (value === "compliant") return "success";
  if (value === "non_compliant") return "danger";
  if (value === "partially_compliant") return "warning";
  return "neutral";
}

function formatMoney(value: string | number | null, currency: string | null): string {
  if (value === null) return "—";
  return `${formatNumber(value)}${currency ? ` ${currency}` : ""}`;
}

function formatNumber(value: string | number | null): string {
  if (value === null) return "—";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return String(value);
  return new Intl.NumberFormat("es-MX", { maximumFractionDigits: 2 }).format(numeric);
}
