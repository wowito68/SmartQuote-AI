import { AlertTriangle, GitCompareArrows, RefreshCcw } from "lucide-react";
import { useEffect, useState } from "react";

import { Button, Card, EmptyState, Section, StatusBadge } from "../../components/ui";
import type { UUID } from "../../lib/types";
import { comparisonApi } from "./api";
import type { Comparison } from "./types";

export function ComparisonPanel({
  tenderId,
  userId,
  onError
}: {
  tenderId: UUID | null;
  userId: UUID;
  onError: (error: unknown) => void;
}) {
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [loading, setLoading] = useState(false);
  const [building, setBuilding] = useState(false);

  useEffect(() => {
    setComparison(null);
    if (tenderId) void load(tenderId);
  }, [tenderId]);

  async function load(id = tenderId) {
    if (!id) return;
    setLoading(true);
    try {
      setComparison(await comparisonApi.latest(id));
    } catch (error) {
      if (error instanceof Error && "status" in error && (error as { status?: number }).status === 404) {
        setComparison(null);
      } else {
        onError(error);
      }
    } finally {
      setLoading(false);
    }
  }

  async function build() {
    if (!tenderId) return;
    setBuilding(true);
    try {
      setComparison(await comparisonApi.generate(tenderId, userId));
    } catch (error) {
      onError(error);
    } finally {
      setBuilding(false);
    }
  }

  return (
    <Section
      title="Comparativo"
      eyebrow="Cotizaciones aprobadas"
      description="Compara de forma determinista cobertura, precio, moneda, cantidad, cumplimiento y entrega. No asigna puntuacion ni ganador."
      action={
        <>
          <Button variant="secondary" disabled={!tenderId} onClick={() => void load()}>
            <RefreshCcw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            Refrescar
          </Button>
          <Button disabled={!tenderId} loading={building} onClick={() => void build()}>
            <GitCompareArrows className="h-4 w-4" />
            Generar comparativo
          </Button>
        </>
      }
    >
      {!tenderId ? (
        <EmptyState title="Sin licitacion seleccionada" detail="Selecciona una licitacion para comparar sus cotizaciones aprobadas." />
      ) : !comparison ? (
        <EmptyState
          icon={<GitCompareArrows className="h-5 w-5" />}
          title="Comparativo aun no generado"
          detail="Se requiere un catalogo aprobado y al menos una cotizacion aprobada."
          action={<Button onClick={() => void build()}>Generar comparativo</Button>}
        />
      ) : (
        <div className="grid gap-4">
          <Card className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="font-semibold">Reglas v{comparison.comparison_version}</p>
              <p className="mt-1 text-xs text-text-secondary">
                Catalogo v{comparison.catalog_version} · {comparison.source_quote_ids.length} cotizaciones fuente
              </p>
            </div>
            <StatusBadge value={comparison.status} />
          </Card>

          {comparison.status === "invalid" ? (
            <div className="flex gap-3 rounded-panel border border-red-200 bg-red-50 p-4 text-sm text-red-800">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <p>Existen inconsistencias criticas. El resultado se conserva para auditoria, pero no se considera comparable de forma confiable.</p>
            </div>
          ) : null}

          {comparison.warnings.length ? (
            <Card>
              <p className="font-medium">Advertencias generales</p>
              <ul className="mt-2 grid gap-1 text-sm text-text-secondary">
                {comparison.warnings.map((warning, index) => (
                  <li key={`${warning.code}-${index}`}>[{warning.severity}] {warning.message}</li>
                ))}
              </ul>
            </Card>
          ) : null}

          <div className="overflow-x-auto rounded-panel border border-border-subtle bg-white">
            <table className="min-w-[1100px] w-full border-collapse text-sm">
              <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-text-secondary">
                <tr>
                  <th className="p-3">Producto solicitado</th>
                  <th className="p-3">Proveedor</th>
                  <th className="p-3">Producto cotizado</th>
                  <th className="p-3">Cantidad</th>
                  <th className="p-3">Precio unitario</th>
                  <th className="p-3">Total</th>
                  <th className="p-3">Cumplimiento</th>
                  <th className="p-3">Entrega</th>
                  <th className="p-3">Observaciones</th>
                </tr>
              </thead>
              <tbody>
                {comparison.items.flatMap((item) =>
                  item.offers.map((offer, offerIndex) => (
                    <tr key={offer.id} className="border-t border-border-subtle align-top">
                      <td className="p-3">
                        {offerIndex === 0 ? (
                          <>
                            <p className="font-medium">{item.requested_product}</p>
                            <p className="text-xs text-text-secondary">
                              {item.requested_quantity ?? "?"} {item.requested_unit ?? "unidad desconocida"}
                            </p>
                            {item.monetary_status === "requires_normalization" ? (
                              <p className="mt-1 text-xs font-medium text-amber-700">Monedas distintas: requiere normalizacion; no se aplico FX.</p>
                            ) : null}
                          </>
                        ) : null}
                      </td>
                      <td className="p-3 font-medium">{offer.supplier_name}</td>
                      <td className="p-3">
                        {offer.status === "missing" ? (
                          <span className="font-medium text-amber-700">No cotizado</span>
                        ) : offer.status === "invalid" ? (
                          <span className="font-medium text-red-700">Inconsistente</span>
                        ) : (
                          <>
                            <p>{offer.quoted_product_name ?? "Sin nombre"}</p>
                            <p className="text-xs text-text-secondary">{[offer.brand, offer.model].filter(Boolean).join(" · ") || "Sin marca/modelo"}</p>
                          </>
                        )}
                      </td>
                      <td className="p-3">
                        {offer.quantity ?? "—"} {offer.unit ?? ""}
                        {offer.quantity_status !== "matched" && offer.status === "quoted" ? (
                          <p className="text-xs text-amber-700">{offer.quantity_status}</p>
                        ) : null}
                      </td>
                      <td className="p-3">{offer.unit_price ?? "—"} {offer.currency ?? ""}</td>
                      <td className="p-3">{offer.total_price ?? "—"} {offer.currency ?? ""}</td>
                      <td className="p-3"><StatusBadge value={offer.compliance} /></td>
                      <td className="p-3">
                        {offer.delivery_days !== null ? `${offer.delivery_days} dias` : offer.delivery_original_text ?? "Desconocida"}
                      </td>
                      <td className="p-3">
                        <p>{offer.observations ?? offer.commercial_terms ?? "—"}</p>
                        {offer.warnings.length ? (
                          <ul className="mt-2 text-xs text-amber-700">
                            {offer.warnings.map((warning, index) => (
                              <li key={`${warning.code}-${index}`}>{warning.message}</li>
                            ))}
                          </ul>
                        ) : null}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Section>
  );
}
