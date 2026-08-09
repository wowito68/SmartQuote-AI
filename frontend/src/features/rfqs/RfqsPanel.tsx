import {
  AlertTriangle,
  Check,
  Clock,
  Eye,
  History,
  Mail,
  Pencil,
  Plus,
  RefreshCcw,
  RotateCcw,
  Send,
  X
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  Button,
  Card,
  DataTable,
  EmptyState,
  Field,
  Modal,
  Section,
  StatusBadge,
  TextInput,
  Textarea
} from "../../components/ui";
import { api } from "../../lib/api";
import { formatDate } from "../../lib/format";
import type {
  Rfq,
  RfqMessages,
  RfqVersions,
  TenderCatalog,
  TenderDocument,
  TenderRfqs,
  TenderSupplier,
  TenderSuppliers,
  UUID
} from "../../lib/types";

export function RfqsPanel({
  tenderId,
  userId,
  documents,
  rfqs,
  loading,
  onRefresh,
  onGenerate,
  onApprove,
  onSend
}: {
  tenderId: UUID | null;
  userId: UUID;
  documents: TenderDocument[];
  rfqs: TenderRfqs | null;
  loading: boolean;
  onRefresh: () => Promise<void>;
  onGenerate: (deadline: string, observations: string | null, documentIds: UUID[]) => Promise<void>;
  onApprove: (rfqId: UUID) => Promise<void>;
  onSend: (rfqId: UUID) => Promise<void>;
}) {
  // The legacy batch callback remains in the component contract so older screens keep compiling.
  // Iteration 11 generation uses the explicit single-RFQ endpoint instead.
  void onGenerate;
  const [modalOpen, setModalOpen] = useState(false);
  const [detailRfq, setDetailRfq] = useState<Rfq | null>(null);
  const items = rfqs?.rfqs ?? [];

  async function refreshAndClose() {
    await onRefresh();
    setModalOpen(false);
  }

  return (
    <Section
      title="RFQs"
      eyebrow="Solicitudes de cotización"
      description="Genera, revisa, aprueba y envía una solicitud explícita por proveedor y contacto."
      action={
        <>
          <Button variant="secondary" onClick={() => void onRefresh()}>
            <RefreshCcw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            Refrescar
          </Button>
          <Button disabled={!tenderId} onClick={() => setModalOpen(true)}>
            <Plus className="h-4 w-4" />
            Nueva RFQ
          </Button>
        </>
      }
    >
      {!tenderId ? (
        <EmptyState title="Sin licitación seleccionada" detail="Selecciona una licitación." />
      ) : (
        <div className="grid gap-5">
          <div className="grid gap-3 md:grid-cols-4">
            <Metric label="Total" value={rfqs?.metrics.total ?? 0} />
            <Metric label="Pendientes" value={rfqs?.metrics.pending_review ?? 0} />
            <Metric label="Aprobadas" value={rfqs?.metrics.approved ?? 0} />
            <Metric label="Enviadas" value={rfqs?.metrics.sent ?? 0} />
          </div>

          {items.length === 0 ? (
            <EmptyState
              icon={<Mail className="h-5 w-5" />}
              title="No hay RFQs"
              detail="Selecciona un proveedor aprobado, un contacto válido y productos aprobados."
              action={<Button onClick={() => setModalOpen(true)}>Nueva RFQ</Button>}
            />
          ) : (
            <>
              <div className="hidden lg:block">
                <DataTable
                  headers={[
                    "Asunto",
                    "Estado",
                    "Destinatario",
                    "Productos",
                    "Fecha límite",
                    "Adjuntos",
                    "Acciones"
                  ]}
                >
                  {items.map((rfq) => (
                    <tr key={rfq.id} className="hover:bg-slate-50">
                      <td className="max-w-[340px] px-4 py-3">
                        <p className="truncate font-semibold text-text-primary">{rfq.subject}</p>
                        <p className="mt-1 truncate text-xs text-text-secondary">
                          Versión {rfq.version} · {formatDate(rfq.created_at)}
                        </p>
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge value={rfq.status} />
                      </td>
                      <td className="max-w-[240px] px-4 py-3 text-text-secondary">
                        <span className="line-clamp-2">
                          {rfq.to_recipients.join(", ") || "Sin destinatario"}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-text-secondary">{rfq.products.length}</td>
                      <td className="px-4 py-3 text-text-secondary">
                        {formatDate(rfq.response_deadline)}
                      </td>
                      <td className="px-4 py-3 text-text-secondary">{rfq.attachments.length}</td>
                      <td className="px-4 py-3">
                        <RfqActions
                          rfq={rfq}
                          onOpen={() => setDetailRfq(rfq)}
                          onRefresh={onRefresh}
                          onApprove={onApprove}
                          onSend={onSend}
                          userId={userId}
                        />
                      </td>
                    </tr>
                  ))}
                </DataTable>
              </div>
              <div className="grid gap-3 lg:hidden">
                {items.map((rfq) => (
                  <RfqCard
                    key={rfq.id}
                    rfq={rfq}
                    userId={userId}
                    onOpen={() => setDetailRfq(rfq)}
                    onRefresh={onRefresh}
                    onApprove={onApprove}
                    onSend={onSend}
                  />
                ))}
              </div>
            </>
          )}

          <GenerateRfqModal
            open={modalOpen}
            tenderId={tenderId}
            userId={userId}
            documents={documents}
            onClose={() => setModalOpen(false)}
            onCreated={refreshAndClose}
          />
          <RfqDetailModal
            rfq={detailRfq}
            userId={userId}
            onClose={() => setDetailRfq(null)}
            onRefresh={async () => {
              await onRefresh();
              if (detailRfq) {
                setDetailRfq(await api.getRfq(detailRfq.id));
              }
            }}
          />
        </div>
      )}
    </Section>
  );
}

function GenerateRfqModal({
  open,
  tenderId,
  userId,
  documents,
  onClose,
  onCreated
}: {
  open: boolean;
  tenderId: UUID;
  userId: UUID;
  documents: TenderDocument[];
  onClose: () => void;
  onCreated: () => Promise<void>;
}) {
  const [suppliers, setSuppliers] = useState<TenderSuppliers | null>(null);
  const [catalog, setCatalog] = useState<TenderCatalog | null>(null);
  const [supplierId, setSupplierId] = useState("");
  const [contactId, setContactId] = useState("");
  const [selectedProducts, setSelectedProducts] = useState<UUID[]>([]);
  const [selectedDocuments, setSelectedDocuments] = useState<UUID[]>([]);
  const [deadline, setDeadline] = useState("");
  const [observations, setObservations] = useState("");
  const [currency, setCurrency] = useState("MXN");
  const [commercialTerms, setCommercialTerms] = useState("");
  const [quoteValidity, setQuoteValidity] = useState("30 días");
  const [responseInstructions, setResponseInstructions] = useState("");
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    void Promise.all([api.listSuppliers(tenderId), api.getCatalog(tenderId)])
      .then(([supplierPayload, catalogPayload]) => {
        setSuppliers(supplierPayload);
        setCatalog(catalogPayload);
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : String(reason)));
  }, [open, tenderId]);

  const approvedSuppliers = useMemo(
    () => (suppliers?.suppliers ?? []).filter((item) => item.status === "approved"),
    [suppliers]
  );
  const selectedSupplier = approvedSuppliers.find((item) => item.supplier_id === supplierId) ?? null;
  const emailContacts = (selectedSupplier?.contacts ?? []).filter(
    (contact) => contact.contact_type === "email" && Boolean(contact.source_url)
  );
  const approvedProducts = (catalog?.products ?? []).filter((item) => item.status === "approved");

  async function generate() {
    if (!supplierId) return setError("Selecciona un proveedor aprobado.");
    if (!contactId) return setError("Selecciona un contacto de correo válido.");
    if (selectedProducts.length === 0) return setError("Selecciona al menos un producto aprobado.");
    if (!deadline) return setError("La fecha límite es obligatoria.");
    setGenerating(true);
    setError("");
    try {
      await api.generateRfq(tenderId, {
        supplier_id: supplierId,
        contact_id: contactId,
        product_ids: selectedProducts,
        document_ids: selectedDocuments,
        generated_by_user_id: userId,
        response_deadline: new Date(deadline).toISOString(),
        observations: observations.trim() || null,
        requested_currency: currency.trim() || null,
        commercial_terms: commercialTerms.trim() || null,
        quote_validity: quoteValidity.trim() || null,
        response_instructions: responseInstructions.trim() || null
      });
      await onCreated();
      setSupplierId("");
      setContactId("");
      setSelectedProducts([]);
      setSelectedDocuments([]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setGenerating(false);
    }
  }

  return (
    <Modal
      open={open}
      title="Nueva RFQ"
      description="La solicitud se crea como borrador. No se enviará nada en este paso."
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button loading={generating} onClick={() => void generate()}>Generar borrador</Button>
        </>
      }
    >
      <div className="grid gap-4">
        {error ? <Warning>{error}</Warning> : null}
        <Field label="Proveedor aprobado">
          <select
            className="w-full rounded-control border border-border-subtle bg-white px-3 py-2 text-sm"
            value={supplierId}
            onChange={(event) => {
              setSupplierId(event.target.value);
              setContactId("");
            }}
          >
            <option value="">Selecciona proveedor</option>
            {approvedSuppliers.map((supplier) => (
              <option key={supplier.id} value={supplier.supplier_id}>
                {supplier.trade_name || supplier.legal_name || supplier.supplier_id}
              </option>
            ))}
          </select>
        </Field>
        {selectedSupplier && emailContacts.length === 0 ? (
          <Warning>El proveedor no tiene un contacto email trazable. No se puede generar la RFQ.</Warning>
        ) : null}
        <Field label="Contacto y destinatario">
          <select
            className="w-full rounded-control border border-border-subtle bg-white px-3 py-2 text-sm"
            value={contactId}
            onChange={(event) => setContactId(event.target.value)}
            disabled={!selectedSupplier}
          >
            <option value="">Selecciona contacto</option>
            {emailContacts.map((contact) => (
              <option key={contact.id} value={contact.id}>
                {contact.contact_name ? `${contact.contact_name} — ` : ""}{contact.value}
              </option>
            ))}
          </select>
        </Field>
        {contactId ? (
          <p className="text-xs text-text-secondary">
            Fuente del contacto: {emailContacts.find((item) => item.id === contactId)?.source_url}
          </p>
        ) : null}

        <ChoiceGroup title="Productos aprobados" warning="Selecciona únicamente las partidas que deseas cotizar.">
          {approvedProducts.map((product) => (
            <label key={product.id} className="flex gap-2 rounded-control border border-border-subtle p-3 text-sm">
              <input
                type="checkbox"
                checked={selectedProducts.includes(product.id)}
                onChange={() => toggleValue(product.id, selectedProducts, setSelectedProducts)}
              />
              <span>
                <span className="font-medium text-text-primary">{product.name}</span>
                <span className="block text-xs text-text-secondary">
                  Cantidad: {product.quantity ?? "sin cantidad"} {product.unit ?? ""}
                </span>
              </span>
            </label>
          ))}
        </ChoiceGroup>

        <ChoiceGroup title="Documentos adjuntos" warning="No se adjunta ningún documento automáticamente.">
          {documents.map((document) => (
            <label key={document.id} className="flex gap-2 rounded-control border border-border-subtle p-3 text-sm">
              <input
                type="checkbox"
                checked={selectedDocuments.includes(document.id)}
                onChange={() => toggleValue(document.id, selectedDocuments, setSelectedDocuments)}
              />
              <span>{document.original_file_name}</span>
            </label>
          ))}
        </ChoiceGroup>

        <Field label="Fecha límite de respuesta">
          <TextInput type="datetime-local" value={deadline} onChange={(event) => setDeadline(event.target.value)} />
        </Field>
        <Field label="Moneda solicitada"><TextInput value={currency} onChange={(event) => setCurrency(event.target.value)} /></Field>
        <Field label="Condiciones comerciales"><Textarea value={commercialTerms} onChange={(event) => setCommercialTerms(event.target.value)} /></Field>
        <Field label="Vigencia solicitada"><TextInput value={quoteValidity} onChange={(event) => setQuoteValidity(event.target.value)} /></Field>
        <Field label="Instrucciones de respuesta"><Textarea value={responseInstructions} onChange={(event) => setResponseInstructions(event.target.value)} /></Field>
        <Field label="Observaciones"><Textarea value={observations} onChange={(event) => setObservations(event.target.value)} /></Field>
      </div>
    </Modal>
  );
}

function RfqDetailModal({
  rfq,
  userId,
  onClose,
  onRefresh
}: {
  rfq: Rfq | null;
  userId: UUID;
  onClose: () => void;
  onRefresh: () => Promise<void>;
}) {
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [versions, setVersions] = useState<RfqVersions | null>(null);
  const [messages, setMessages] = useState<RfqMessages | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!rfq) return;
    setSubject(rfq.subject);
    setBody(rfq.body);
    void Promise.all([api.getRfqVersions(rfq.id), api.getRfqMessages(rfq.id)]).then(
      ([versionPayload, messagePayload]) => {
        setVersions(versionPayload);
        setMessages(messagePayload);
      }
    );
  }, [rfq]);

  if (!rfq) return null;
  const editable = rfq.status === "draft";

  async function save() {
    setBusy(true);
    try {
      await api.updateRfq(rfq!.id, {
        changed_by_user_id: userId,
        subject,
        body,
        change_reason: "Edición manual antes de aprobación"
      });
      await onRefresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open title={`RFQ v${rfq.version}`} description="Contenido, adjuntos, versiones y resultado de entrega." onClose={onClose}>
      <div className="grid gap-4">
        <div className="grid gap-2 rounded-panel border border-border-subtle p-3 text-sm">
          <span><strong>Estado:</strong> {rfq.status}</span>
          <span><strong>Destinatario:</strong> {rfq.to_recipients.join(", ") || "Sin destinatario"}</span>
          <span><strong>Productos:</strong> {rfq.products.length}</span>
          <span><strong>Adjuntos:</strong> {rfq.attachments.map((item) => item.original_file_name).join(", ") || "Ninguno"}</span>
        </div>
        <Field label="Asunto"><TextInput disabled={!editable} value={subject} onChange={(event) => setSubject(event.target.value)} /></Field>
        <Field label="Cuerpo"><Textarea disabled={!editable} rows={14} value={body} onChange={(event) => setBody(event.target.value)} /></Field>
        {editable ? <Button loading={busy} onClick={() => void save()}><Pencil className="h-4 w-4" />Guardar nueva versión</Button> : null}
        <div>
          <p className="mb-2 flex items-center gap-2 text-sm font-semibold"><History className="h-4 w-4" />Historial de versiones</p>
          <div className="grid gap-2">
            {(versions?.versions ?? []).map((version) => (
              <div key={version.id} className="rounded-control border border-border-subtle p-3 text-sm">
                <strong>v{version.version}</strong> · {version.status} · {formatDate(version.created_at)}
                {version.change_reason ? <span className="block text-xs text-text-secondary">{version.change_reason}</span> : null}
              </div>
            ))}
          </div>
        </div>
        <div>
          <p className="mb-2 text-sm font-semibold">Resultado de envío</p>
          {(messages?.messages ?? []).length === 0 ? (
            <p className="text-sm text-text-secondary">Aún no existe un intento de envío.</p>
          ) : (
            messages!.messages.map((message) => (
              <div key={message.id} className="rounded-control border border-border-subtle p-3 text-sm">
                <StatusBadge value={message.status} />
                <p className="mt-2">Proveedor: {message.provider_name}</p>
                <p>ID externo: {message.external_message_id || "No disponible"}</p>
                {message.error_message ? <p className="text-red-700">{message.error_message}</p> : null}
              </div>
            ))
          )}
        </div>
      </div>
    </Modal>
  );
}

function RfqCard({ rfq, userId, onOpen, onRefresh, onApprove, onSend }: {
  rfq: Rfq;
  userId: UUID;
  onOpen: () => void;
  onRefresh: () => Promise<void>;
  onApprove: (rfqId: UUID) => Promise<void>;
  onSend: (rfqId: UUID) => Promise<void>;
}) {
  return (
    <Card className="grid gap-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-semibold text-text-primary">{rfq.subject}</p>
          <p className="mt-1 text-sm text-text-secondary">{rfq.to_recipients.join(", ")}</p>
        </div>
        <StatusBadge value={rfq.status} />
      </div>
      <div className="flex items-center gap-2 text-sm text-text-secondary">
        <Clock className="h-4 w-4 text-brand-teal" />{formatDate(rfq.response_deadline)}
      </div>
      <RfqActions rfq={rfq} userId={userId} onOpen={onOpen} onRefresh={onRefresh} onApprove={onApprove} onSend={onSend} />
    </Card>
  );
}

function RfqActions({ rfq, userId, onOpen, onRefresh, onApprove, onSend }: {
  rfq: Rfq;
  userId: UUID;
  onOpen: () => void;
  onRefresh: () => Promise<void>;
  onApprove: (rfqId: UUID) => Promise<void>;
  onSend: (rfqId: UUID) => Promise<void>;
}) {
  const [busy, setBusy] = useState<string | null>(null);

  async function run(name: string, action: () => Promise<unknown>) {
    setBusy(name);
    try {
      await action();
      await onRefresh();
    } finally {
      setBusy(null);
    }
  }

  async function send() {
    const confirmed = window.confirm("Esta acción enviará una solicitud real al proveedor.");
    if (!confirmed) return;
    await run("send", () => onSend(rfq.id));
  }

  return (
    <div className="flex flex-wrap gap-2">
      <Button size="sm" variant="secondary" onClick={onOpen}><Eye className="h-4 w-4" />Ver</Button>
      {rfq.status === "draft" ? (
        <Button size="sm" variant="secondary" loading={busy === "review"} onClick={() => void run("review", () => api.submitRfqReview(rfq.id, userId))}>
          <Check className="h-4 w-4" />Enviar a revisión
        </Button>
      ) : null}
      {rfq.status === "pending_review" ? (
        <>
          <Button size="sm" variant="secondary" loading={busy === "approve"} onClick={() => void run("approve", () => onApprove(rfq.id))}>
            <Check className="h-4 w-4" />Aprobar
          </Button>
          <Button size="sm" variant="secondary" loading={busy === "reject"} onClick={() => {
            const reason = window.prompt("Motivo para devolver la RFQ a borrador:");
            if (reason) void run("reject", () => api.rejectRfq(rfq.id, userId, reason));
          }}><X className="h-4 w-4" />Rechazar</Button>
        </>
      ) : null}
      {rfq.status === "approved" ? (
        <Button size="sm" loading={busy === "send"} onClick={() => void send()}><Send className="h-4 w-4" />Enviar</Button>
      ) : null}
      {rfq.status === "failed" || rfq.status === "retry_pending" ? (
        <Button size="sm" loading={busy === "retry"} onClick={() => void run("retry", () => api.retryRfq(rfq.id, userId))}>
          <RotateCcw className="h-4 w-4" />Reintentar
        </Button>
      ) : null}
      {["draft", "pending_review", "approved", "failed", "retry_pending"].includes(rfq.status) ? (
        <Button size="sm" variant="secondary" loading={busy === "cancel"} onClick={() => void run("cancel", () => api.cancelRfq(rfq.id, userId, "Cancelado por el usuario"))}>
          <X className="h-4 w-4" />Cancelar
        </Button>
      ) : null}
    </div>
  );
}

function ChoiceGroup({ title, warning, children }: { title: string; warning: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-1 text-sm font-medium text-slate-700">{title}</p>
      <p className="mb-2 text-xs text-text-secondary">{warning}</p>
      <div className="grid max-h-48 gap-2 overflow-auto">{children}</div>
    </div>
  );
}

function Warning({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex gap-2 rounded-control border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{children}
    </div>
  );
}

function toggleValue(value: UUID, current: UUID[], setCurrent: (value: UUID[]) => void) {
  setCurrent(current.includes(value) ? current.filter((item) => item !== value) : [...current, value]);
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-panel border border-border-subtle bg-slate-50 p-4">
      <p className="text-xs font-medium uppercase tracking-normal text-text-secondary">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-text-primary">{value}</p>
    </div>
  );
}
