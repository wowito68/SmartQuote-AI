import { Check, RefreshCcw, ShieldCheck, Sparkles, X } from "lucide-react";
import { useState } from "react";

import { Button, DataTable, EmptyState, Section, StatusBadge } from "../../components/ui";
import { asPercent } from "../../lib/format";
import type { CatalogProduct, TenderCatalog, UUID } from "../../lib/types";

export function CatalogPanel({
  tenderId,
  catalog,
  loading,
  onRefresh,
  onApproveProduct,
  onRejectProduct,
  onApproveCatalog
}: {
  tenderId: UUID | null;
  catalog: TenderCatalog | null;
  loading: boolean;
  onRefresh: () => Promise<void>;
  onApproveProduct: (productId: UUID) => Promise<void>;
  onRejectProduct: (productId: UUID, reason: string) => Promise<void>;
  onApproveCatalog: () => Promise<void>;
}) {
  const [busyId, setBusyId] = useState<string | null>(null);

  async function approveProduct(id: UUID) {
    setBusyId(id);
    try {
      await onApproveProduct(id);
    } finally {
      setBusyId(null);
    }
  }

  async function rejectProduct(id: UUID) {
    const reason = window.prompt("Motivo de rechazo", "No cumple especificacion");
    if (!reason) return;
    setBusyId(id);
    try {
      await onRejectProduct(id, reason);
    } finally {
      setBusyId(null);
    }
  }

  const products = catalog?.products ?? [];

  return (
    <Section
      title="Catalogo"
      eyebrow="Revision humana"
      description="Productos extraidos por IA con confianza, evidencia y estado de aprobacion."
      action={
        <>
          <Button variant="secondary" onClick={() => void onRefresh()}>
            <RefreshCcw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            Refrescar
          </Button>
          <Button
            disabled={!tenderId || products.length === 0}
            onClick={() => void onApproveCatalog()}
          >
            <ShieldCheck className="h-4 w-4" />
            Aprobar catalogo
          </Button>
        </>
      }
    >
      {!tenderId ? (
        <EmptyState title="Sin licitacion seleccionada" detail="Selecciona una licitacion." />
      ) : products.length === 0 ? (
        <EmptyState
          icon={<Sparkles className="h-5 w-5" />}
          title="Catalogo pendiente"
          detail="Ejecuta la extraccion desde documentos para revisar los productos solicitados."
        />
      ) : (
        <div className="grid gap-5">
          <div className="grid gap-3 md:grid-cols-4">
            <Metric label="Total" value={catalog?.metrics.products_total ?? 0} />
            <Metric label="Pendientes" value={catalog?.metrics.products_pending_review ?? 0} />
            <Metric label="Aprobados" value={catalog?.metrics.products_approved ?? 0} />
            <Metric
              label="Confianza promedio"
              value={asPercent((catalog?.metrics.average_confidence ?? 0) * 100)}
            />
          </div>

          <div className="hidden lg:block">
            <DataTable
              headers={[
                "Producto",
                "Cantidad",
                "Categoria",
                "Confianza",
                "Estado",
                "Acciones"
              ]}
            >
              {products.map((product) => (
                <tr key={product.id} className="hover:bg-slate-50">
                  <td className="max-w-[420px] px-4 py-3">
                    <p className="truncate font-semibold text-text-primary">{product.name}</p>
                    <p className="mt-1 line-clamp-2 text-xs text-text-secondary">
                      {product.description || "Sin descripcion"}
                    </p>
                  </td>
                  <td className="px-4 py-3 text-text-secondary">
                    {product.quantity ?? "-"} {product.unit ?? ""}
                  </td>
                  <td className="px-4 py-3 text-text-secondary">{product.category ?? "-"}</td>
                  <td className="px-4 py-3">
                    <Confidence value={product.confidence} />
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge value={product.status} />
                  </td>
                  <td className="px-4 py-3">
                    <ProductActions
                      product={product}
                      busy={busyId === product.id}
                      onApprove={approveProduct}
                      onReject={rejectProduct}
                    />
                  </td>
                </tr>
              ))}
            </DataTable>
          </div>

          <div className="grid gap-3 lg:hidden">
            {products.map((product) => (
              <div key={product.id} className="rounded-panel border border-border-subtle bg-white p-4 shadow-panel">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-semibold text-text-primary">{product.name}</p>
                    <p className="mt-1 text-sm text-text-secondary">
                      {product.quantity ?? "-"} {product.unit ?? ""} · {product.category ?? "Sin categoria"}
                    </p>
                  </div>
                  <StatusBadge value={product.status} />
                </div>
                <div className="mt-3">
                  <Confidence value={product.confidence} />
                </div>
                <div className="mt-3">
                  <ProductActions
                    product={product}
                    busy={busyId === product.id}
                    onApprove={approveProduct}
                    onReject={rejectProduct}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </Section>
  );
}

function ProductActions({
  product,
  busy,
  onApprove,
  onReject
}: {
  product: CatalogProduct;
  busy: boolean;
  onApprove: (id: UUID) => Promise<void>;
  onReject: (id: UUID) => Promise<void>;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      <Button size="sm" variant="secondary" loading={busy} onClick={() => void onApprove(product.id)}>
        <Check className="h-4 w-4" />
        Aprobar
      </Button>
      <Button size="sm" variant="ghost" disabled={busy} onClick={() => void onReject(product.id)}>
        <X className="h-4 w-4" />
        Rechazar
      </Button>
    </div>
  );
}

function Confidence({ value }: { value: number }) {
  const percentage = Math.round(value * 100);
  return (
    <div className="grid w-36 gap-1">
      <div className="h-2 overflow-hidden rounded-full bg-slate-100">
        <div className="h-full rounded-full bg-brand-teal" style={{ width: `${percentage}%` }} />
      </div>
      <span className="text-xs text-text-secondary">{percentage}%</span>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-panel border border-border-subtle bg-slate-50 p-4">
      <p className="text-xs font-medium uppercase tracking-normal text-text-secondary">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-text-primary">{value}</p>
    </div>
  );
}

