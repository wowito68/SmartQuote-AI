import { Check, Clock, Mail, Plus, RefreshCcw, Send } from "lucide-react";
import { useState } from "react";

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
import { formatDate } from "../../lib/format";
import type { Rfq, TenderDocument, TenderRfqs, UUID } from "../../lib/types";

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
  const [modalOpen, setModalOpen] = useState(false);
  const items = rfqs?.rfqs ?? [];

  return (
    <Section
      title="RFQs"
      eyebrow="Solicitudes de cotizacion"
      description="Borradores, aprobaciones, adjuntos e intentos de entrega por proveedor."
      action={
        <>
          <Button variant="secondary" onClick={() => void onRefresh()}>
            <RefreshCcw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            Refrescar
          </Button>
          <Button disabled={!tenderId} onClick={() => setModalOpen(true)}>
            <Plus className="h-4 w-4" />
            Generar RFQs
          </Button>
        </>
      }
    >
      {!tenderId ? (
        <EmptyState title="Sin licitacion seleccionada" detail="Selecciona una licitacion." />
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
              detail="Aprueba proveedores y genera solicitudes para revisar antes del envio."
              action={<Button onClick={() => setModalOpen(true)}>Generar RFQs</Button>}
            />
          ) : (
            <>
              <div className="hidden lg:block">
                <DataTable headers={["Asunto", "Estado", "Destinatarios", "Fecha limite", "Adjuntos", "Acciones"]}>
                  {items.map((rfq) => (
                    <tr key={rfq.id} className="hover:bg-slate-50">
                      <td className="max-w-[380px] px-4 py-3">
                        <p className="truncate font-semibold text-text-primary">{rfq.subject}</p>
                        <p className="mt-1 truncate text-xs text-text-secondary">
                          Version {rfq.version} · {formatDate(rfq.created_at)}
                        </p>
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge value={rfq.status} />
                      </td>
                      <td className="max-w-[260px] px-4 py-3 text-text-secondary">
                        <span className="line-clamp-2">{rfq.to_recipients.join(", ") || "Sin destinatarios"}</span>
                      </td>
                      <td className="px-4 py-3 text-text-secondary">{formatDate(rfq.response_deadline)}</td>
                      <td className="px-4 py-3 text-text-secondary">{rfq.attachments.length}</td>
                      <td className="px-4 py-3">
                        <RfqActions rfq={rfq} onApprove={onApprove} onSend={onSend} />
                      </td>
                    </tr>
                  ))}
                </DataTable>
              </div>
              <div className="grid gap-3 lg:hidden">
                {items.map((rfq) => (
                  <RfqCard key={rfq.id} rfq={rfq} onApprove={onApprove} onSend={onSend} />
                ))}
              </div>
            </>
          )}

          <GenerateRfqsModal
            open={modalOpen}
            userId={userId}
            documents={documents}
            onClose={() => setModalOpen(false)}
            onGenerate={async (deadline, observations, documentIds) => {
              await onGenerate(deadline, observations, documentIds);
              setModalOpen(false);
            }}
          />
        </div>
      )}
    </Section>
  );
}

function GenerateRfqsModal({
  open,
  userId,
  documents,
  onClose,
  onGenerate
}: {
  open: boolean;
  userId: UUID;
  documents: TenderDocument[];
  onClose: () => void;
  onGenerate: (deadline: string, observations: string | null, documentIds: UUID[]) => Promise<void>;
}) {
  const [deadline, setDeadline] = useState("");
  const [observations, setObservations] = useState("");
  const [selectedDocuments, setSelectedDocuments] = useState<UUID[]>([]);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");

  async function generate() {
    if (!deadline) {
      setError("La fecha limite es obligatoria.");
      return;
    }
    setGenerating(true);
    try {
      await onGenerate(new Date(deadline).toISOString(), observations.trim() || null, selectedDocuments);
      setObservations("");
      setError("");
    } finally {
      setGenerating(false);
    }
  }

  return (
    <Modal
      open={open}
      title="Generar RFQs"
      description="Crea borradores revisables para proveedores aprobados."
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button disabled={!userId} loading={generating} onClick={() => void generate()}>
            Generar
          </Button>
        </>
      }
    >
      <div className="grid gap-4">
        <Field label="Fecha limite de respuesta" error={error}>
          <TextInput
            type="datetime-local"
            value={deadline}
            onChange={(event) => {
              setDeadline(event.target.value);
              setError("");
            }}
          />
        </Field>
        <Field label="Observaciones">
          <Textarea
            value={observations}
            onChange={(event) => setObservations(event.target.value)}
            placeholder="Condiciones, notas o instrucciones para proveedores."
          />
        </Field>
        {documents.length > 0 ? (
          <div>
            <p className="mb-2 text-sm font-medium text-slate-700">Adjuntos</p>
            <div className="flex flex-wrap gap-2">
              {documents.map((document) => {
                const active = selectedDocuments.includes(document.id);
                return (
                  <button
                    key={document.id}
                    className={`rounded-control border px-3 py-2 text-sm transition ${
                      active
                        ? "border-brand-teal bg-brand-teal text-white"
                        : "border-border-subtle bg-white text-text-secondary hover:bg-slate-50"
                    }`}
                    type="button"
                    onClick={() =>
                      setSelectedDocuments((current) =>
                        active
                          ? current.filter((id) => id !== document.id)
                          : [...current, document.id]
                      )
                    }
                  >
                    {document.original_file_name}
                  </button>
                );
              })}
            </div>
          </div>
        ) : null}
      </div>
    </Modal>
  );
}

function RfqCard({
  rfq,
  onApprove,
  onSend
}: {
  rfq: Rfq;
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
        <Clock className="h-4 w-4 text-brand-teal" />
        {formatDate(rfq.response_deadline)}
      </div>
      <RfqActions rfq={rfq} onApprove={onApprove} onSend={onSend} />
    </Card>
  );
}

function RfqActions({
  rfq,
  onApprove,
  onSend
}: {
  rfq: Rfq;
  onApprove: (rfqId: UUID) => Promise<void>;
  onSend: (rfqId: UUID) => Promise<void>;
}) {
  const [busy, setBusy] = useState<string | null>(null);

  async function approve() {
    setBusy("approve");
    try {
      await onApprove(rfq.id);
    } finally {
      setBusy(null);
    }
  }

  async function send() {
    setBusy("send");
    try {
      await onSend(rfq.id);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-wrap gap-2">
      <Button size="sm" variant="secondary" loading={busy === "approve"} onClick={() => void approve()}>
        <Check className="h-4 w-4" />
        Aprobar
      </Button>
      <Button size="sm" loading={busy === "send"} onClick={() => void send()}>
        <Send className="h-4 w-4" />
        Enviar
      </Button>
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

