import { AlertTriangle, Check, FileSearch, RefreshCcw, RotateCcw, Upload, X } from "lucide-react";
import { useMemo, useState } from "react";

import { Button, Card, EmptyState, Field, Modal, Section, StatusBadge, TextInput, Textarea } from "../../components/ui";
import { formatDate } from "../../lib/format";
import type { CatalogProduct, TenderRfqs, TenderSuppliers, UUID } from "../../lib/types";
import { quoteApi } from "./api";
import type { Quote, QuoteEvidence, QuoteItem } from "./types";

export function QuotesPanel({
  tenderId,
  userId,
  suppliers,
  rfqs,
  catalogProducts,
  quotes,
  loading,
  onRefresh,
  onError
}: {
  tenderId: UUID | null;
  userId: UUID;
  suppliers: TenderSuppliers | null;
  rfqs: TenderRfqs | null;
  catalogProducts: CatalogProduct[];
  quotes: Quote[];
  loading: boolean;
  onRefresh: () => Promise<void>;
  onError: (error: unknown) => void;
}) {
  const [uploadOpen, setUploadOpen] = useState(false);
  const [selectedQuoteId, setSelectedQuoteId] = useState<UUID | null>(quotes[0]?.id ?? null);
  const selected = quotes.find((quote) => quote.id === selectedQuoteId) ?? quotes[0] ?? null;

  return (
    <Section
      title="Cotizaciones"
      eyebrow="Recepcion y analisis manual"
      description="Carga PDF, XLSX o DOCX; revisa incertidumbre y evidencia antes de aprobar."
      action={
        <>
          <Button variant="secondary" onClick={() => void onRefresh()}>
            <RefreshCcw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            Refrescar
          </Button>
          <Button disabled={!tenderId} onClick={() => setUploadOpen(true)}>
            <Upload className="h-4 w-4" />
            Cargar cotizacion
          </Button>
        </>
      }
    >
      {!tenderId ? (
        <EmptyState title="Sin licitacion seleccionada" detail="Selecciona una licitacion para recibir cotizaciones." />
      ) : quotes.length === 0 ? (
        <EmptyState
          icon={<FileSearch className="h-5 w-5" />}
          title="No hay cotizaciones"
          detail="Cuando recibas una cotizacion externamente, cargala aqui para analizarla."
          action={<Button onClick={() => setUploadOpen(true)}>Cargar cotizacion</Button>}
        />
      ) : (
        <div className="grid gap-5 xl:grid-cols-[320px_minmax(0,1fr)]">
          <div className="grid content-start gap-2">
            {quotes.map((quote) => (
              <button
                key={quote.id}
                type="button"
                onClick={() => setSelectedQuoteId(quote.id)}
                className={`rounded-panel border p-4 text-left transition ${
                  selected?.id === quote.id ? "border-brand-teal bg-teal-50" : "border-border-subtle bg-white hover:bg-slate-50"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <p className="min-w-0 truncate font-semibold">{quote.original_file_name}</p>
                  <StatusBadge value={quote.status} />
                </div>
                <p className="mt-2 text-xs text-text-secondary">{formatDate(quote.received_at)}</p>
                <p className="mt-1 text-xs text-text-secondary">{quote.items.length} items · v{quote.version}</p>
              </button>
            ))}
          </div>
          {selected ? (
            <QuoteReview
              quote={selected}
              userId={userId}
              catalogProducts={catalogProducts}
              onChanged={onRefresh}
              onError={onError}
            />
          ) : null}
        </div>
      )}

      <UploadQuoteModal
        open={uploadOpen}
        tenderId={tenderId}
        userId={userId}
        suppliers={suppliers}
        rfqs={rfqs}
        onClose={() => setUploadOpen(false)}
        onUploaded={async () => {
          setUploadOpen(false);
          await onRefresh();
        }}
        onError={onError}
      />
    </Section>
  );
}

function UploadQuoteModal({
  open,
  tenderId,
  userId,
  suppliers,
  rfqs,
  onClose,
  onUploaded,
  onError
}: {
  open: boolean;
  tenderId: UUID | null;
  userId: UUID;
  suppliers: TenderSuppliers | null;
  rfqs: TenderRfqs | null;
  onClose: () => void;
  onUploaded: () => Promise<void>;
  onError: (error: unknown) => void;
}) {
  const approved = useMemo(
    () => (suppliers?.suppliers ?? []).filter((supplier) => ["approved", "contacted", "responded"].includes(supplier.status)),
    [suppliers]
  );
  const [supplierId, setSupplierId] = useState("");
  const [rfqId, setRfqId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const matchingRfqs = (rfqs?.rfqs ?? []).filter(
    (rfq) => rfq.supplier_id === supplierId && ["sent", "delivered", "responded"].includes(rfq.status)
  );

  async function upload() {
    if (!tenderId || !supplierId || !file) return;
    setBusy(true);
    try {
      await quoteApi.upload(tenderId, userId, supplierId, rfqId || null, file);
      await onUploaded();
      setFile(null);
      setSupplierId("");
      setRfqId("");
    } catch (error) {
      onError(error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={open}
      title="Cargar cotizacion recibida"
      description="La recepcion es manual. El archivo se almacena de forma privada y despues se procesa asincronamente."
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button loading={busy} disabled={!supplierId || !file} onClick={() => void upload()}>Cargar y analizar</Button>
        </>
      }
    >
      <div className="grid gap-4">
        <Field label="Proveedor aprobado">
          <select className="h-10 w-full rounded-control border border-border-subtle bg-white px-3 text-sm" value={supplierId} onChange={(event) => { setSupplierId(event.target.value); setRfqId(""); }}>
            <option value="">Seleccionar proveedor</option>
            {approved.map((supplier) => (
              <option key={supplier.id} value={supplier.supplier_id}>
                {supplier.trade_name || supplier.legal_name || supplier.supplier_id}
              </option>
            ))}
          </select>
        </Field>
        <Field label="RFQ enviada">
          <select className="h-10 w-full rounded-control border border-border-subtle bg-white px-3 text-sm" value={rfqId} onChange={(event) => setRfqId(event.target.value)}>
            <option value="">Usar RFQ enviada mas reciente</option>
            {matchingRfqs.map((rfq) => <option key={rfq.id} value={rfq.id}>v{rfq.version} · {rfq.subject}</option>)}
          </select>
        </Field>
        <Field label="Archivo PDF, XLSX o DOCX">
          <input
            className="block w-full text-sm text-text-secondary file:mr-3 file:rounded-control file:border-0 file:bg-slate-100 file:px-3 file:py-2"
            type="file"
            accept=".pdf,.xlsx,.docx,application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
        </Field>
        <p className="text-xs text-text-secondary">No se ejecutan macros ni contenido embebido. XLSX y DOCX se leen como datos.</p>
      </div>
    </Modal>
  );
}

function QuoteReview({
  quote,
  userId,
  catalogProducts,
  onChanged,
  onError
}: {
  quote: Quote;
  userId: UUID;
  catalogProducts: CatalogProduct[];
  onChanged: () => Promise<void>;
  onError: (error: unknown) => void;
}) {
  const [editItem, setEditItem] = useState<QuoteItem | null>(null);
  const [evidence, setEvidence] = useState<QuoteEvidence[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");

  async function action(name: string, fn: () => Promise<unknown>) {
    setBusy(name);
    try {
      await fn();
      await onChanged();
    } catch (error) {
      onError(error);
    } finally {
      setBusy(null);
    }
  }

  async function loadEvidence() {
    try {
      setEvidence((await quoteApi.evidence(quote.id)).items);
    } catch (error) {
      onError(error);
    }
  }

  const warnings = Array.from(new Set(quote.items.flatMap((item) => item.warnings)));
  return (
    <div className="grid gap-4">
      <Card className="grid gap-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="font-semibold">{quote.original_file_name}</h3>
            <p className="mt-1 text-sm text-text-secondary">Moneda: {quote.currency ?? "desconocida"} · Total: {quote.total_amount ?? "no encontrado"}</p>
          </div>
          <StatusBadge value={quote.status} />
        </div>
        {quote.last_error ? <p className="rounded-control bg-red-50 p-3 text-sm text-red-700">{quote.last_error}</p> : null}
        {warnings.length ? (
          <div className="rounded-control border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
            <p className="font-medium">Requiere atencion</p>
            <p className="mt-1">{warnings.join(" · ")}</p>
          </div>
        ) : null}
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="secondary" onClick={() => void loadEvidence()}><FileSearch className="h-4 w-4" />Ver evidencia</Button>
          {quote.status === "pending_review" ? (
            <>
              <Button size="sm" loading={busy === "approve"} onClick={() => void action("approve", () => quoteApi.approve(quote.id, userId))}><Check className="h-4 w-4" />Aprobar</Button>
              <Button size="sm" variant="secondary" loading={busy === "reject"} onClick={() => void action("reject", () => quoteApi.reject(quote.id, userId, rejectReason || "Rechazada durante revision"))}><X className="h-4 w-4" />Rechazar</Button>
            </>
          ) : null}
          {["pending_review", "rejected", "failed"].includes(quote.status) ? (
            <Button size="sm" variant="secondary" loading={busy === "reprocess"} onClick={() => void action("reprocess", () => quoteApi.reprocess(quote.id, userId))}><RotateCcw className="h-4 w-4" />Reprocess</Button>
          ) : null}
        </div>
        {quote.status === "pending_review" ? (
          <Field label="Motivo de rechazo (si aplica)"><TextInput value={rejectReason} onChange={(event) => setRejectReason(event.target.value)} /></Field>
        ) : null}
        <div className="grid gap-2 text-xs text-text-secondary sm:grid-cols-3">
          <span>Documento: {quote.documents[0]?.document_type?.toUpperCase() ?? "-"}</span>
          <span>Run: {quote.extraction_runs.at(-1)?.run_number ?? "-"}</span>
          <span>IA: {quote.extraction_runs.at(-1)?.model ?? "-"}</span>
        </div>
      </Card>

      <div className="grid gap-3">
        {quote.items.map((item) => {
          const requested = catalogProducts.find((product) => product.id === item.catalog_product_id);
          return (
            <Card key={item.id} className="grid gap-3">
              <div className="flex flex-wrap justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-xs font-medium uppercase text-text-secondary">Producto solicitado</p>
                  <p className="font-semibold">{requested?.name ?? "Sin asociar"}</p>
                  <p className="mt-2 text-xs font-medium uppercase text-text-secondary">Producto cotizado</p>
                  <p className="font-semibold">{item.product_name}</p>
                </div>
                <div className="flex gap-2"><StatusBadge value={item.match_status} /><StatusBadge value={item.compliance_status} /></div>
              </div>
              <div className="grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
                <Value label="Cantidad" value={`${item.quantity ?? "?"} ${item.unit ?? ""}`} />
                <Value label="Marca / modelo" value={`${item.brand ?? "?"} / ${item.model ?? "?"}`} />
                <Value label="Precio" value={`${item.unit_price ?? "?"} ${item.currency ?? "?"}`} />
                <Value label="Entrega" value={item.delivery_days == null ? "?" : `${item.delivery_days} dias`} />
              </div>
              <div className="flex flex-wrap items-center gap-2 text-xs text-text-secondary">
                <span>Confidence {(item.confidence * 100).toFixed(0)}%</span>
                <span>Match {(item.match_score * 100).toFixed(0)}%</span>
                {item.warnings.map((warning) => <span key={warning} className="rounded-full bg-amber-100 px-2 py-1 text-amber-800">{warning}</span>)}
              </div>
              {item.evidence_fragment ? <p className="border-l-2 border-brand-teal pl-3 text-sm text-text-secondary">{item.evidence_fragment}</p> : null}
              {quote.status === "pending_review" ? <Button size="sm" variant="secondary" onClick={() => setEditItem(item)}>Corregir item</Button> : null}
            </Card>
          );
        })}
      </div>

      {evidence.length ? (
        <Card>
          <h3 className="font-semibold">Evidencia trazable</h3>
          <div className="mt-3 grid gap-2">
            {evidence.map((entry) => (
              <div key={entry.id} className="rounded-control border border-border-subtle p-3 text-sm">
                <div className="flex flex-wrap justify-between gap-2"><strong>{entry.field_name}</strong><span className="text-text-secondary">{entry.locator} · {entry.finding_status}</span></div>
                <p className="mt-1 text-text-secondary">{entry.fragment || "Sin fragmento para campo no encontrado"}</p>
              </div>
            ))}
          </div>
        </Card>
      ) : null}

      {editItem ? (
        <EditItemModal
          item={editItem}
          quoteId={quote.id}
          userId={userId}
          catalogProducts={catalogProducts}
          onClose={() => setEditItem(null)}
          onSaved={async () => { setEditItem(null); await onChanged(); }}
          onError={onError}
        />
      ) : null}
    </div>
  );
}

function EditItemModal({ item, quoteId, userId, catalogProducts, onClose, onSaved, onError }: {
  item: QuoteItem; quoteId: UUID; userId: UUID; catalogProducts: CatalogProduct[]; onClose: () => void; onSaved: () => Promise<void>; onError: (error: unknown) => void;
}) {
  const [productId, setProductId] = useState(item.catalog_product_id ?? "");
  const [brand, setBrand] = useState(item.brand ?? "");
  const [model, setModel] = useState(item.model ?? "");
  const [quantity, setQuantity] = useState(item.quantity == null ? "" : String(item.quantity));
  const [unit, setUnit] = useState(item.unit ?? "");
  const [unitPrice, setUnitPrice] = useState(item.unit_price == null ? "" : String(item.unit_price));
  const [totalPrice, setTotalPrice] = useState(item.total_price == null ? "" : String(item.total_price));
  const [currency, setCurrency] = useState(item.currency ?? "");
  const [delivery, setDelivery] = useState(item.delivery_days == null ? "" : String(item.delivery_days));
  const [compliance, setCompliance] = useState(item.compliance_status);
  const [notes, setNotes] = useState(item.notes ?? "");
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    try {
      await quoteApi.updateItem(quoteId, item.id, {
        changed_by_user_id: userId,
        catalog_product_id: productId || null,
        brand: brand || null,
        model: model || null,
        quantity: quantity ? Number(quantity) : null,
        unit: unit || null,
        unit_price: unitPrice ? Number(unitPrice) : null,
        total_price: totalPrice ? Number(totalPrice) : null,
        currency: currency || null,
        delivery_days: delivery ? Number(delivery) : null,
        compliance_status: compliance,
        notes: notes || null
      });
      await onSaved();
    } catch (error) {
      onError(error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open title="Corregir QuoteItem" description="La evidencia original no se sobrescribe; la correccion queda auditada." onClose={onClose} footer={<><Button variant="secondary" onClick={onClose}>Cancelar</Button><Button loading={busy} onClick={() => void save()}>Guardar correccion</Button></>}>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Producto solicitado"><select className="h-10 w-full rounded-control border border-border-subtle px-3 text-sm" value={productId} onChange={(event) => setProductId(event.target.value)}><option value="">Sin asociar</option>{catalogProducts.filter((product) => product.status === "approved").map((product) => <option key={product.id} value={product.id}>{product.name}</option>)}</select></Field>
        <Field label="Marca"><TextInput value={brand} onChange={(event) => setBrand(event.target.value)} /></Field>
        <Field label="Modelo"><TextInput value={model} onChange={(event) => setModel(event.target.value)} /></Field>
        <Field label="Cantidad"><TextInput type="number" value={quantity} onChange={(event) => setQuantity(event.target.value)} /></Field>
        <Field label="Unidad"><TextInput value={unit} onChange={(event) => setUnit(event.target.value)} /></Field>
        <Field label="Precio unitario"><TextInput type="number" value={unitPrice} onChange={(event) => setUnitPrice(event.target.value)} /></Field>
        <Field label="Precio total"><TextInput type="number" value={totalPrice} onChange={(event) => setTotalPrice(event.target.value)} /></Field>
        <Field label="Moneda"><TextInput value={currency} maxLength={3} onChange={(event) => setCurrency(event.target.value.toUpperCase())} /></Field>
        <Field label="Entrega (dias)"><TextInput type="number" value={delivery} onChange={(event) => setDelivery(event.target.value)} /></Field>
        <Field label="Cumplimiento"><select className="h-10 w-full rounded-control border border-border-subtle px-3 text-sm" value={compliance} onChange={(event) => setCompliance(event.target.value as QuoteItem["compliance_status"])}><option value="compliant">Cumple</option><option value="non_compliant">No cumple</option><option value="partial">Parcial</option><option value="unknown">Desconocido</option></select></Field>
        <div className="sm:col-span-2"><Field label="Notas"><Textarea value={notes} onChange={(event) => setNotes(event.target.value)} /></Field></div>
      </div>
    </Modal>
  );
}

function Value({ label, value }: { label: string; value: string }) {
  return <div><p className="text-xs uppercase text-text-secondary">{label}</p><p className="mt-1 font-medium">{value}</p></div>;
}
