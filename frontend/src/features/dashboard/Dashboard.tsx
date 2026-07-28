import type { ReactNode } from "react";
import { Activity, BarChart3, Database, Mail, Server, Workflow } from "lucide-react";

import { Card, EmptyState, Section, StatusBadge } from "../../components/ui";
import { asPercent, formatDate } from "../../lib/format";
import type { Tender, TenderCatalog, TenderRfqs, TenderSuppliers } from "../../lib/types";

export function Dashboard({
  tenders,
  health,
  catalog,
  suppliers,
  rfqs
}: {
  tenders: Tender[];
  health: { status: string; project_name: string; version: string; environment: string } | null;
  catalog: TenderCatalog | null;
  suppliers: TenderSuppliers | null;
  rfqs: TenderRfqs | null;
}) {
  const active = tenders.length;
  const inReview = tenders.filter((item) => item.status.includes("review")).length;

  return (
    <div className="grid gap-6">
      <Section
        title="Tablero operativo"
        eyebrow="Resumen"
        description="Indicadores principales del proceso de compra seleccionado y salud del sistema."
      >
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <Kpi icon={<Workflow />} label="Licitaciones activas" value={active.toString()} />
          <Kpi icon={<Activity />} label="En revision" value={inReview.toString()} />
          <Kpi
            icon={<Database />}
            label="Productos aprobados"
            value={(catalog?.metrics.products_approved ?? 0).toString()}
          />
          <Kpi icon={<Mail />} label="RFQs enviadas" value={(rfqs?.metrics.sent ?? 0).toString()} />
        </div>
      </Section>

      <div className="grid gap-4 xl:grid-cols-[1fr_360px]">
        <Section title="Licitaciones recientes" eyebrow="Actividad">
          {tenders.length === 0 ? (
            <EmptyState
              icon={<BarChart3 className="h-5 w-5" />}
              title="No hay licitaciones todavia"
              detail="Crea tu primera licitacion para comenzar a cargar documentos y construir el catalogo."
            />
          ) : (
            <Card padding="none">
              <div className="divide-y divide-border-subtle">
                {tenders.slice(0, 6).map((tender) => (
                  <div
                    key={tender.id}
                    className="grid gap-3 px-4 py-4 md:grid-cols-[1fr_auto_auto] md:items-center"
                  >
                    <div className="min-w-0">
                      <p className="truncate font-semibold text-text-primary">{tender.title}</p>
                      <p className="mt-1 line-clamp-1 text-sm text-text-secondary">
                        {tender.description || "Sin descripcion"}
                      </p>
                    </div>
                    <StatusBadge value={tender.status} />
                    <p className="text-sm text-text-secondary">{formatDate(tender.deadline)}</p>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </Section>

        <Section title="Servicios" eyebrow="Sistema">
          <div className="grid gap-3">
            <Card>
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-panel bg-brand-tealSoft text-brand-teal">
                    <Server className="h-5 w-5" />
                  </div>
                  <div>
                    <p className="font-semibold text-text-primary">Backend</p>
                    <p className="text-sm text-text-secondary">
                      {health?.version ?? "Sin version"} · {health?.environment ?? "sin entorno"}
                    </p>
                  </div>
                </div>
                <StatusBadge value={health?.status ?? "offline"} />
              </div>
            </Card>
            <Card>
              <p className="text-sm font-semibold text-text-primary">Calidad de proveedores</p>
              <p className="mt-3 text-3xl font-semibold text-text-primary">
                {asPercent(suppliers?.metrics.valid_contact_percentage ?? 0)}
              </p>
              <p className="text-sm text-text-secondary">con contacto valido</p>
            </Card>
            <Card>
              <p className="text-sm font-semibold text-text-primary">Entrega RFQ</p>
              <p className="mt-3 text-3xl font-semibold text-text-primary">
                {asPercent(rfqs?.metrics.success_percentage ?? 0)}
              </p>
              <p className="text-sm text-text-secondary">tasa de exito registrada</p>
            </Card>
          </div>
        </Section>
      </div>
    </div>
  );
}

function Kpi({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <Card>
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-text-secondary">{label}</p>
        <div className="text-brand-teal [&>svg]:h-5 [&>svg]:w-5">{icon}</div>
      </div>
      <p className="mt-3 text-3xl font-semibold text-text-primary">{value}</p>
    </Card>
  );
}

