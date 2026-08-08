import { Check, Globe2, Mail, MapPin, Plus, RefreshCcw, Search, X } from "lucide-react";
import { useState } from "react";

import {
  Button,
  Card,
  EmptyState,
  Field,
  Modal,
  Section,
  StatusBadge,
  TextInput
} from "../../components/ui";
import type { TenderSupplier, TenderSuppliers, UUID } from "../../lib/types";

export function SuppliersPanel({
  tenderId,
  userId,
  suppliers,
  loading,
  onRefresh,
  onDiscover,
  onCreateManual,
  onApprove,
  onReject
}: {
  tenderId: UUID | null;
  userId: UUID;
  suppliers: TenderSuppliers | null;
  loading: boolean;
  onRefresh: () => Promise<void>;
  onDiscover: () => Promise<void>;
  onCreateManual: (payload: ManualSupplierForm) => Promise<void>;
  onApprove: (supplierId: UUID) => Promise<void>;
  onReject: (supplierId: UUID, reason: string) => Promise<void>;
}) {
  const [modalOpen, setModalOpen] = useState(false);
  const [discovering, setDiscovering] = useState(false);

  async function discover() {
    setDiscovering(true);
    try {
      await onDiscover();
    } finally {
      setDiscovering(false);
    }
  }

  const items = suppliers?.suppliers ?? [];

  return (
    <Section
      title="Proveedores"
      eyebrow="Busqueda y aprobacion"
      description="Candidatos por licitacion, contactos, fuentes, coincidencias y revision humana."
      action={
        <>
          <Button variant="secondary" onClick={() => void onRefresh()}>
            <RefreshCcw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            Refrescar
          </Button>
          <Button disabled={!tenderId} loading={discovering} onClick={() => void discover()}>
            <Search className="h-4 w-4" />
            Buscar
          </Button>
          <Button disabled={!tenderId} onClick={() => setModalOpen(true)}>
            <Plus className="h-4 w-4" />
            Manual
          </Button>
        </>
      }
    >
      {!tenderId ? (
        <EmptyState title="Sin licitacion seleccionada" detail="Selecciona una licitacion." />
      ) : (
        <div className="grid gap-5">
          <div className="grid gap-3 md:grid-cols-4">
            <Metric label="Total" value={suppliers?.metrics.suppliers_total ?? 0} />
            <Metric label="Aprobados" value={suppliers?.metrics.suppliers_approved ?? 0} />
            <Metric label="Pendientes" value={suppliers?.metrics.suppliers_pending_review ?? 0} />
            <Metric label="Con contacto" value={suppliers?.metrics.suppliers_with_valid_contact ?? 0} />
          </div>

          {items.length === 0 ? (
            <EmptyState
              icon={<Search className="h-5 w-5" />}
              title="No hay proveedores"
              detail="Agrega proveedores manualmente o ejecuta la busqueda despues de aprobar el catalogo."
              action={<Button onClick={() => setModalOpen(true)}>Agregar proveedor</Button>}
            />
          ) : (
            <div className="grid gap-3 xl:grid-cols-2">
              {items.map((supplier) => (
                <SupplierCard
                  key={supplier.id}
                  supplier={supplier}
                  onApprove={onApprove}
                  onReject={onReject}
                />
              ))}
            </div>
          )}

          <ManualSupplierModal
            open={modalOpen}
            userId={userId}
            onClose={() => setModalOpen(false)}
            onCreate={async (form) => {
              await onCreateManual(form);
              setModalOpen(false);
            }}
          />
        </div>
      )}
    </Section>
  );
}

export type ManualSupplierForm = {
  legalName: string;
  tradeName: string;
  website: string;
  email: string;
  phone: string;
  category: string;
  country: string;
  city: string;
};

function SupplierCard({
  supplier,
  onApprove,
  onReject
}: {
  supplier: TenderSupplier;
  onApprove: (supplierId: UUID) => Promise<void>;
  onReject: (supplierId: UUID, reason: string) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const name = supplier.trade_name || supplier.legal_name || "Proveedor sin nombre";
  const email = supplier.contacts.find((contact) => contact.contact_type === "email");
  const bestMatch = [...supplier.matches].sort((left, right) => right.score - left.score)[0];
  const bestScore = bestMatch?.score ?? 0;
  const source = supplier.sources[0];

  async function approve() {
    setBusy(true);
    try {
      await onApprove(supplier.id);
    } finally {
      setBusy(false);
    }
  }

  async function reject() {
    const reason = window.prompt("Motivo de rechazo", "No cumple criterios de compra");
    if (!reason) return;
    setBusy(true);
    try {
      await onReject(supplier.id, reason);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="grid gap-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate text-base font-semibold text-text-primary">{name}</h3>
            <StatusBadge value={supplier.status} />
            {supplier.is_manual ? <StatusBadge value="manual" /> : null}
          </div>
          <p className="mt-1 text-sm text-text-secondary">
            {supplier.legal_name && supplier.trade_name
              ? supplier.legal_name
              : supplier.category || "Sin categoria"}
          </p>
        </div>
        <div className="rounded-panel bg-slate-50 px-3 py-2 text-right">
          <p className="text-xs text-text-secondary">Score</p>
          <p className="text-sm font-semibold text-text-primary">{Math.round(bestScore)}</p>
        </div>
      </div>

      <div className="grid gap-2 text-sm text-text-secondary">
        <span className="flex min-w-0 items-center gap-2">
          <Mail className="h-4 w-4 shrink-0 text-brand-teal" />
          <span className="truncate">{email?.value || "Sin correo registrado"}</span>
        </span>
        <span className="flex min-w-0 items-center gap-2">
          <Globe2 className="h-4 w-4 shrink-0 text-brand-teal" />
          <span className="truncate">{supplier.website || "Sin sitio web"}</span>
        </span>
        <span className="flex min-w-0 items-center gap-2">
          <MapPin className="h-4 w-4 shrink-0 text-brand-teal" />
          <span className="truncate">
            {supplier.city || "Sin ciudad"}, {supplier.country || "Sin pais"}
          </span>
        </span>
      </div>

      <div className="grid gap-2 rounded-panel border border-border-subtle bg-slate-50 p-3 text-xs text-text-secondary">
        <p>
          <span className="font-semibold text-text-primary">Fuente:</span>{" "}
          {source?.source_title || source?.source_name || source?.provider_name || "Sin fuente registrada"}
        </p>
        {source?.source_url ? <p className="truncate">{source.source_url}</p> : null}
        {source?.query ? (
          <p>
            <span className="font-semibold text-text-primary">Consulta:</span> {source.query}
          </p>
        ) : null}
        <p>
          <span className="font-semibold text-text-primary">Por que coincide:</span>{" "}
          {bestMatch?.reason || bestMatch?.reasons?.[0] || "Sin razon de coincidencia disponible"}
        </p>
      </div>

      <div className="flex flex-wrap gap-2 border-t border-border-subtle pt-4">
        <Button size="sm" variant="secondary" loading={busy} onClick={() => void approve()}>
          <Check className="h-4 w-4" />
          Aprobar
        </Button>
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => void reject()}>
          <X className="h-4 w-4" />
          Rechazar
        </Button>
      </div>
    </Card>
  );
}

function ManualSupplierModal({
  open,
  userId,
  onClose,
  onCreate
}: {
  open: boolean;
  userId: UUID;
  onClose: () => void;
  onCreate: (payload: ManualSupplierForm) => Promise<void>;
}) {
  const [form, setForm] = useState<ManualSupplierForm>({
    legalName: "",
    tradeName: "",
    website: "",
    email: "",
    phone: "",
    category: "",
    country: "MX",
    city: ""
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function createManual() {
    if (!form.legalName.trim() && !form.tradeName.trim()) {
      setError("Agrega razon social o nombre comercial.");
      return;
    }
    setSaving(true);
    try {
      await onCreate(form);
      setForm({
        legalName: "",
        tradeName: "",
        website: "",
        email: "",
        phone: "",
        category: "",
        country: "MX",
        city: ""
      });
      setError("");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      open={open}
      title="Agregar proveedor manual"
      description="Registra un proveedor conocido para esta licitacion."
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button disabled={!userId} loading={saving} onClick={() => void createManual()}>
            Agregar proveedor
          </Button>
        </>
      }
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Razon social" error={error}>
          <TextInput
            value={form.legalName}
            onChange={(event) => {
              setForm({ ...form, legalName: event.target.value });
              setError("");
            }}
          />
        </Field>
        <Field label="Nombre comercial">
          <TextInput
            value={form.tradeName}
            onChange={(event) => setForm({ ...form, tradeName: event.target.value })}
          />
        </Field>
        <Field label="Correo">
          <TextInput
            value={form.email}
            onChange={(event) => setForm({ ...form, email: event.target.value })}
          />
        </Field>
        <Field label="Telefono">
          <TextInput
            value={form.phone}
            onChange={(event) => setForm({ ...form, phone: event.target.value })}
          />
        </Field>
        <Field label="Sitio web">
          <TextInput
            value={form.website}
            onChange={(event) => setForm({ ...form, website: event.target.value })}
          />
        </Field>
        <Field label="Categoria">
          <TextInput
            value={form.category}
            onChange={(event) => setForm({ ...form, category: event.target.value })}
          />
        </Field>
        <Field label="Pais">
          <TextInput
            value={form.country}
            onChange={(event) => setForm({ ...form, country: event.target.value })}
          />
        </Field>
        <Field label="Ciudad">
          <TextInput
            value={form.city}
            onChange={(event) => setForm({ ...form, city: event.target.value })}
          />
        </Field>
      </div>
    </Modal>
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
