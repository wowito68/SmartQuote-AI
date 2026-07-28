import {
  Archive,
  CalendarDays,
  ClipboardList,
  FileText,
  Filter,
  FolderClosed,
  Plus,
  Search,
  SortAsc,
  Workflow
} from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";

import {
  Alert,
  Button,
  Card,
  ConfirmationDialog,
  DataTable,
  EmptyState,
  Field,
  Modal,
  Pagination,
  Section,
  Select,
  StatusBadge,
  Tabs,
  TextInput,
  Textarea
} from "../../components/ui";
import { compactId, formatDate } from "../../lib/format";
import type { Tender, TenderCatalog, TenderDocument, TenderRfqs, TenderSuppliers, UUID } from "../../lib/types";

type DetailTab = "summary" | "documents" | "catalog" | "suppliers" | "rfqs" | "activity";

const pageSize = 8;

export function TenderWorkspace({
  tenders,
  selectedTenderId,
  userId,
  loading,
  documents,
  catalog,
  suppliers,
  rfqs,
  documentsPanel,
  catalogPanel,
  suppliersPanel,
  rfqsPanel,
  onSelectTender,
  onCreateTender,
  onArchiveTender,
  onRefresh
}: {
  tenders: Tender[];
  selectedTenderId: UUID | null;
  userId: UUID;
  loading: boolean;
  documents: TenderDocument[];
  catalog: TenderCatalog | null;
  suppliers: TenderSuppliers | null;
  rfqs: TenderRfqs | null;
  documentsPanel: ReactNode;
  catalogPanel: ReactNode;
  suppliersPanel: ReactNode;
  rfqsPanel: ReactNode;
  onSelectTender: (id: UUID) => void;
  onCreateTender: (payload: {
    title: string;
    description: string | null;
    deadline: string | null;
    created_by_user_id: UUID;
  }) => Promise<void>;
  onArchiveTender: (id: UUID) => Promise<void>;
  onRefresh: () => Promise<void>;
}) {
  const [createOpen, setCreateOpen] = useState(false);
  const [archiveId, setArchiveId] = useState<UUID | null>(null);
  const [archiving, setArchiving] = useState(false);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [sort, setSort] = useState("updated_desc");
  const [page, setPage] = useState(1);
  const [activeTab, setActiveTab] = useState<DetailTab>("summary");

  const selectedTender = tenders.find((item) => item.id === selectedTenderId) ?? null;

  const filtered = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return tenders
      .filter((tender) => {
        const matchesQuery =
          !normalizedQuery ||
          tender.title.toLowerCase().includes(normalizedQuery) ||
          (tender.description ?? "").toLowerCase().includes(normalizedQuery);
        const matchesStatus = statusFilter === "all" || tender.status === statusFilter;
        return matchesQuery && matchesStatus;
      })
      .sort((a, b) => {
        if (sort === "deadline_asc") {
          return (a.deadline ?? "").localeCompare(b.deadline ?? "");
        }
        if (sort === "title_asc") {
          return a.title.localeCompare(b.title);
        }
        return b.updated_at.localeCompare(a.updated_at);
      });
  }, [query, sort, statusFilter, tenders]);

  const totalPages = Math.max(Math.ceil(filtered.length / pageSize), 1);
  const pageItems = filtered.slice((page - 1) * pageSize, page * pageSize);
  const statuses = Array.from(new Set(tenders.map((tender) => tender.status)));

  async function confirmArchive() {
    if (!archiveId) return;
    setArchiving(true);
    try {
      await onArchiveTender(archiveId);
      setArchiveId(null);
    } finally {
      setArchiving(false);
    }
  }

  return (
    <div className="grid gap-6">
      <Section
        title="Licitaciones"
        eyebrow="Pipeline de compras"
        description="Crea, filtra y revisa el avance de cada proceso de cotizacion."
        action={
          <>
            <Button variant="secondary" loading={loading} onClick={() => void onRefresh()}>
              Refrescar
            </Button>
            <Button onClick={() => setCreateOpen(true)}>
              <Plus className="h-4 w-4" aria-hidden />
              Nueva licitacion
            </Button>
          </>
        }
      >
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          <Metric icon={<ClipboardList />} label="Activas" value={tenders.length} />
          <Metric
            icon={<Workflow />}
            label="Borradores"
            value={tenders.filter((item) => item.status.includes("draft")).length}
          />
          <Metric
            icon={<FolderClosed />}
            label="Cerradas"
            value={tenders.filter((item) => item.status.includes("closed")).length}
          />
          <Metric icon={<FileText />} label="Documentos" value={documents.length} />
          <Metric icon={<CalendarDays />} label="RFQs pendientes" value={rfqs?.metrics.pending_review ?? 0} />
        </div>
      </Section>

      <Card className="grid gap-4">
        <div className="grid gap-3 lg:grid-cols-[1fr_220px_220px]">
          <Field label="Buscar">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
              <TextInput
                className="pl-9"
                value={query}
                onChange={(event) => {
                  setQuery(event.target.value);
                  setPage(1);
                }}
                placeholder="Titulo o descripcion"
              />
            </div>
          </Field>
          <Field label="Estado">
            <div className="relative">
              <Filter className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
              <Select
                className="pl-9"
                value={statusFilter}
                onChange={(event) => {
                  setStatusFilter(event.target.value);
                  setPage(1);
                }}
              >
                <option value="all">Todos</option>
                {statuses.map((status) => (
                  <option key={status} value={status}>
                    {status}
                  </option>
                ))}
              </Select>
            </div>
          </Field>
          <Field label="Orden">
            <div className="relative">
              <SortAsc className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
              <Select className="pl-9" value={sort} onChange={(event) => setSort(event.target.value)}>
                <option value="updated_desc">Actualizacion reciente</option>
                <option value="deadline_asc">Fecha limite</option>
                <option value="title_asc">Titulo A-Z</option>
              </Select>
            </div>
          </Field>
        </div>

        <div className="flex items-center justify-between gap-3 text-sm text-text-secondary">
          <span>{filtered.length} resultados</span>
          <span>{selectedTender ? `Seleccionada: ${selectedTender.title}` : "Sin seleccion"}</span>
        </div>

        {filtered.length === 0 ? (
          <EmptyState
            title="No hay licitaciones con esos filtros"
            detail="Ajusta la busqueda o crea una nueva licitacion para empezar."
            action={<Button onClick={() => setCreateOpen(true)}>Nueva licitacion</Button>}
          />
        ) : (
          <>
            <div className="hidden lg:block">
              <DataTable
                headers={[
                  "Licitacion",
                  "Estado",
                  "Fecha limite",
                  "Documentos",
                  "Productos",
                  "Proveedores",
                  "RFQs",
                  "Acciones"
                ]}
              >
                {pageItems.map((tender) => (
                  <tr key={tender.id} className="hover:bg-slate-50">
                    <td className="max-w-[320px] px-4 py-3">
                      <button
                        type="button"
                        className="text-left"
                        onClick={() => onSelectTender(tender.id)}
                      >
                        <span className="block truncate font-semibold text-text-primary">
                          {tender.title}
                        </span>
                        <span className="mt-1 block truncate text-xs text-text-secondary">
                          {tender.description || compactId(tender.id)}
                        </span>
                      </button>
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge value={tender.status} />
                    </td>
                    <td className="px-4 py-3 text-text-secondary">{formatDate(tender.deadline)}</td>
                    <td className="px-4 py-3">{tender.id === selectedTenderId ? documents.length : "-"}</td>
                    <td className="px-4 py-3">{tender.id === selectedTenderId ? (catalog?.products.length ?? 0) : "-"}</td>
                    <td className="px-4 py-3">{tender.id === selectedTenderId ? (suppliers?.suppliers.length ?? 0) : "-"}</td>
                    <td className="px-4 py-3">{tender.id === selectedTenderId ? (rfqs?.rfqs.length ?? 0) : "-"}</td>
                    <td className="px-4 py-3">
                      <div className="flex gap-2">
                        <Button size="sm" variant="secondary" onClick={() => onSelectTender(tender.id)}>
                          Abrir
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setArchiveId(tender.id)}>
                          Archivar
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </DataTable>
            </div>

            <div className="grid gap-3 lg:hidden">
              {pageItems.map((tender) => (
                <button
                  key={tender.id}
                  type="button"
                  className={`rounded-panel border bg-white p-4 text-left shadow-panel ${
                    tender.id === selectedTenderId ? "border-brand-teal" : "border-border-subtle"
                  }`}
                  onClick={() => onSelectTender(tender.id)}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate font-semibold text-text-primary">{tender.title}</p>
                      <p className="mt-1 line-clamp-2 text-sm text-text-secondary">
                        {tender.description || "Sin descripcion"}
                      </p>
                    </div>
                    <StatusBadge value={tender.status} />
                  </div>
                  <p className="mt-3 text-sm text-text-secondary">{formatDate(tender.deadline)}</p>
                </button>
              ))}
            </div>
            <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
          </>
        )}
      </Card>

      <TenderDetail
        tender={selectedTender}
        documents={documents}
        catalog={catalog}
        suppliers={suppliers}
        rfqs={rfqs}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        documentsPanel={documentsPanel}
        catalogPanel={catalogPanel}
        suppliersPanel={suppliersPanel}
        rfqsPanel={rfqsPanel}
        onArchive={() => selectedTender && setArchiveId(selectedTender.id)}
      />

      <CreateTenderModal
        open={createOpen}
        userId={userId}
        onClose={() => setCreateOpen(false)}
        onCreate={async (payload) => {
          await onCreateTender(payload);
          setCreateOpen(false);
        }}
      />

      <ConfirmationDialog
        open={archiveId !== null}
        title="Archivar licitacion"
        detail="La licitacion dejara de aparecer en la lista activa. La auditoria se conserva."
        confirmLabel="Archivar"
        loading={archiving}
        onCancel={() => setArchiveId(null)}
        onConfirm={() => void confirmArchive()}
      />
    </div>
  );
}

function TenderDetail({
  tender,
  documents,
  catalog,
  suppliers,
  rfqs,
  activeTab,
  documentsPanel,
  catalogPanel,
  suppliersPanel,
  rfqsPanel,
  onTabChange,
  onArchive
}: {
  tender: Tender | null;
  documents: TenderDocument[];
  catalog: TenderCatalog | null;
  suppliers: TenderSuppliers | null;
  rfqs: TenderRfqs | null;
  activeTab: DetailTab;
  documentsPanel: ReactNode;
  catalogPanel: ReactNode;
  suppliersPanel: ReactNode;
  rfqsPanel: ReactNode;
  onTabChange: (tab: DetailTab) => void;
  onArchive: () => void;
}) {
  if (!tender) {
    return (
      <EmptyState
        title="Selecciona una licitacion"
        detail="El detalle operativo aparecera aqui con resumen, documentos, catalogo, proveedores, RFQs y actividad."
      />
    );
  }

  const tabs = [
    { key: "summary" as const, label: "Resumen" },
    { key: "documents" as const, label: "Documentos", count: documents.length },
    { key: "catalog" as const, label: "Catalogo", count: catalog?.products.length ?? 0 },
    { key: "suppliers" as const, label: "Proveedores", count: suppliers?.suppliers.length ?? 0 },
    { key: "rfqs" as const, label: "RFQs", count: rfqs?.rfqs.length ?? 0 },
    { key: "activity" as const, label: "Actividad" }
  ];

  return (
    <Card className="grid gap-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <StatusBadge value={tender.status} />
            <span className="text-xs text-text-secondary">{compactId(tender.id)}</span>
          </div>
          <h2 className="text-2xl font-semibold text-text-primary">{tender.title}</h2>
          <p className="mt-2 max-w-4xl text-sm leading-6 text-text-secondary">
            {tender.description || "Sin descripcion registrada."}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={onArchive}>
            <Archive className="h-4 w-4" aria-hidden />
            Archivar
          </Button>
        </div>
      </div>

      <Tabs tabs={tabs} active={activeTab} onChange={onTabChange} />

      {activeTab === "summary" ? (
        <TenderSummary tender={tender} documents={documents} catalog={catalog} suppliers={suppliers} rfqs={rfqs} />
      ) : activeTab === "documents" ? (
        documentsPanel
      ) : activeTab === "catalog" ? (
        catalogPanel
      ) : activeTab === "suppliers" ? (
        suppliersPanel
      ) : activeTab === "rfqs" ? (
        rfqsPanel
      ) : (
        <ActivityPanel tender={tender} documents={documents} catalog={catalog} suppliers={suppliers} rfqs={rfqs} />
      )}
    </Card>
  );
}

function TenderSummary({
  tender,
  documents,
  catalog,
  suppliers,
  rfqs
}: {
  tender: Tender;
  documents: TenderDocument[];
  catalog: TenderCatalog | null;
  suppliers: TenderSuppliers | null;
  rfqs: TenderRfqs | null;
}) {
  const steps = [
    { label: "Licitacion creada", done: true },
    { label: "Documentos cargados", done: documents.length > 0 },
    { label: "Texto extraido", done: documents.some((item) => item.status.includes("ready") || item.status.includes("text")) },
    { label: "Catalogo revisado", done: (catalog?.metrics.products_approved ?? 0) > 0 },
    { label: "Proveedores aprobados", done: (suppliers?.metrics.suppliers_approved ?? 0) > 0 },
    { label: "RFQs generadas", done: (rfqs?.metrics.total ?? 0) > 0 },
    { label: "RFQs enviadas", done: (rfqs?.metrics.sent ?? 0) > 0 }
  ];

  const next = steps.find((step) => !step.done);

  return (
    <div className="grid gap-5">
      <div className="grid gap-3 md:grid-cols-4">
        <Metric icon={<CalendarDays />} label="Fecha limite" value={formatDate(tender.deadline)} />
        <Metric icon={<FileText />} label="Documentos" value={documents.length} />
        <Metric icon={<ClipboardList />} label="Productos" value={catalog?.products.length ?? 0} />
        <Metric icon={<Workflow />} label="RFQs" value={rfqs?.metrics.total ?? 0} />
      </div>
      {next ? (
        <Alert
          tone="info"
          title="Proximo paso"
          detail={`${next.label}. Usa la pestana correspondiente para continuar.`}
        />
      ) : (
        <Alert tone="success" title="Flujo completo" detail="La licitacion ya tiene RFQs enviadas." />
      )}
      <div className="grid gap-3 lg:grid-cols-7">
        {steps.map((step, index) => (
          <div
            key={step.label}
            className={`rounded-panel border p-3 ${
              step.done
                ? "border-emerald-200 bg-semantic-successBg"
                : "border-border-subtle bg-slate-50"
            }`}
          >
            <div className="flex items-center gap-2">
              <span
                className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
                  step.done ? "bg-semantic-success text-white" : "bg-white text-text-secondary"
                }`}
              >
                {index + 1}
              </span>
              <p className="text-sm font-medium text-text-primary">{step.label}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ActivityPanel({
  tender,
  documents,
  catalog,
  suppliers,
  rfqs
}: {
  tender: Tender;
  documents: TenderDocument[];
  catalog: TenderCatalog | null;
  suppliers: TenderSuppliers | null;
  rfqs: TenderRfqs | null;
}) {
  const items = [
    `Licitacion creada el ${formatDate(tender.created_at)}`,
    `${documents.length} documentos registrados`,
    `${catalog?.metrics.products_approved ?? 0} productos aprobados`,
    `${suppliers?.metrics.suppliers_approved ?? 0} proveedores aprobados`,
    `${rfqs?.metrics.sent ?? 0} RFQs enviadas`
  ];

  return (
    <div className="grid gap-2">
      {items.map((item) => (
        <div key={item} className="rounded-panel border border-border-subtle bg-slate-50 px-4 py-3 text-sm text-text-secondary">
          {item}
        </div>
      ))}
    </div>
  );
}

function CreateTenderModal({
  open,
  userId,
  onClose,
  onCreate
}: {
  open: boolean;
  userId: UUID;
  onClose: () => void;
  onCreate: (payload: {
    title: string;
    description: string | null;
    deadline: string | null;
    created_by_user_id: UUID;
  }) => Promise<void>;
}) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [deadline, setDeadline] = useState("");
  const [saving, setSaving] = useState(false);
  const [titleError, setTitleError] = useState("");

  async function submit() {
    if (!title.trim()) {
      setTitleError("El titulo es obligatorio.");
      return;
    }
    setSaving(true);
    try {
      await onCreate({
        title: title.trim(),
        description: description.trim() || null,
        deadline: deadline ? new Date(deadline).toISOString() : null,
        created_by_user_id: userId
      });
      setTitle("");
      setDescription("");
      setDeadline("");
      setTitleError("");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      open={open}
      title="Nueva licitacion"
      description="Registra la oportunidad para cargar documentos y comenzar el pipeline."
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button loading={saving} onClick={() => void submit()}>
            Crear licitacion
          </Button>
        </>
      }
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <Field label="Titulo" error={titleError} hint="Usa un nombre corto y reconocible.">
            <TextInput
              value={title}
              onChange={(event) => {
                setTitle(event.target.value);
                setTitleError("");
              }}
              placeholder="Adquisicion de transformadores 2026"
            />
          </Field>
        </div>
        <div className="sm:col-span-2">
          <Field label="Descripcion" hint="Opcional. Incluye alcance o dependencia solicitante.">
            <Textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Licitacion para suministro nacional..."
            />
          </Field>
        </div>
        <Field label="Fecha limite" hint="Opcional. Se guarda con zona horaria del navegador.">
          <TextInput
            type="datetime-local"
            value={deadline}
            onChange={(event) => setDeadline(event.target.value)}
          />
        </Field>
      </div>
    </Modal>
  );
}

function Metric({ icon, label, value }: { icon: ReactNode; label: string; value: string | number }) {
  return (
    <Card className="flex items-center gap-3" padding="sm">
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-panel bg-brand-tealSoft text-brand-teal [&>svg]:h-5 [&>svg]:w-5">
        {icon}
      </div>
      <div className="min-w-0">
        <p className="truncate text-xs font-medium uppercase tracking-normal text-text-secondary">{label}</p>
        <p className="truncate text-xl font-semibold text-text-primary">{value}</p>
      </div>
    </Card>
  );
}

