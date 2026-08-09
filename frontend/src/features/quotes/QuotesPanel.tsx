import { AlertTriangle, Check, FileSearch, RefreshCcw, RotateCcw, Upload, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Button, Card, EmptyState, Section, StatusBadge, TextInput, Textarea } from "../../components/ui";
import type { TenderCatalog, TenderRfqs, TenderSuppliers, UUID } from "../../lib/types";
import { quoteApi } from "./api";
import type { ProcessingStatus, QuoteDetail, QuoteItem, QuoteSummary } from "./types";

export function QuotesPanel({
  tenderId,
  userId,
  catalog,
  suppliers,
  rfqs
}: {
  tenderId: UUID | null;
  userId: UUID;
  catalog: TenderCatalog | null;
  suppliers: TenderSuppliers | null;
  rfqs: TenderRfqs | null;
}) {
  const [quotes, setQuotes] = useState<QuoteSummary[]>([]);
  const [selectedId, setSelectedId] = useState<UUID | null>(null);
  const [detail, setDetail] = useState<QuoteDetail | null>(null);
  const [processing, setProcessing] = useState<ProcessingStatus | null>(null);
  const [supplierId, setSupplierId] = useState("");
  const [rfqId, setRfqId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const approvedSuppliers = useMemo(
    () => (suppliers?.suppliers ?? []).filter((item) => ["approved", "contacted", "responded"].includes(item.status)),
    [suppliers]
  );
  const eligibleRfqs = useMemo(
    () => (rfqs?.rfqs ?? []).filter(
      (item) => item.tender_supplier_id === supplierId && ["sent", "delivered", "responded"].includes(item.status)
    ),
    [rfqs, supplierId]
  );

  useEffect(() => {
    setQuotes([]);
    setSelectedId(null);
    setDetail(null);
    setProcessing(null);
    setSupplierId("");
    setRfqId("");
    if (tenderId) void refreshQuotes(tenderId);
  }, [tenderId]);

  async function refreshQuotes(id = tenderId) {
    if (!id) return;
    try {
      const result = await quoteApi.list(id);
      setQuotes(result.items);
      if (selectedId) await loadDetail(selectedId);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No fue posible cargar cotizaciones.");
    }
  }

  async function loadDetail(id: UUID) {
    setSelectedId(id);
    try {
      const [quote, status] = await Promise.all([quoteApi.detail(id), quoteApi.processingStatus(id)]);
      setDetail(quote);
      setProcessing(status);
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No fue posible cargar la cotizacion.");
    }
  }

  async function upload() {
    if (!tenderId || !supplierId || !file) {
      setError("Selecciona proveedor y archivo antes de cargar.");
      return;
    }
    setBusy(true);
    try {
      const result = await quoteApi.receive(tenderId, supplierId, rfqId || null, userId, file);
      await refreshQuotes(tenderId);
      await loadDetail(result.quote.id);
      setFile(null);
      setError(result.duplicate ? "Documento duplicado: se reutilizo la cotizacion existente." : "");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No fue posible cargar la cotizacion.");
    } finally {
      setBusy(false);
    }
  }

  async function action(operation: () => Promise<unknown>) {
    if (!detail) return;
    setBusy(true);
    try {
      await operation();
      await refreshQuotes();
      await loadDetail(detail.id);
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "La operacion no pudo completarse.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Section
      title="Cotizaciones"
      eyebrow="Recepcion manual y analisis"
      description="Carga PDF, XLSX o DOCX; revisa incertidumbre, evidencia y correcciones antes de aprobar."
      action={
        <Button variant="secondary" disabled={!tenderId} onClick={() => void refreshQuotes()}>
          <RefreshCcw className="h-4 w-4" /> Refrescar
        </Button>
      }
    >
      {!tenderId ? (
        <EmptyState title="Sin licitacion seleccionada" detail="Selecciona una licitacion para recibir cotizaciones." />
      ) : (
        <div className="grid gap-5 xl:grid-cols-[360px_minmax(0,1fr)]">
          <div className="grid content-start gap-4">
            <Card className="grid gap-3">
              <h3 className="font-semibold">Cargar cotizacion</h3>
              <label className="grid gap-1 text-sm">
                <span className="font-medium">Proveedor aprobado</span>
                <select className="h-10 rounded-control border border-border-subtle bg-white px-3" value={supplierId} onChange={(event) => { setSupplierId(event.target.value); setRfqId(""); }}>
                  <option value="">Seleccionar</option>
                  {approvedSuppliers.map((item) => <option key={item.id} value={item.id}>{item.trade_name || item.legal_name || item.supplier_id}</option>)}
                </select>
              </label>
              <label className="grid gap-1 text-sm">
                <span className="font-medium">RFQ enviada</span>
                <select className="h-10 rounded-control border border-border-subtle bg-white px-3" value={rfqId} onChange={(event) => setRfqId(event.target.value)}>
                  <option value="">Usar ultima RFQ enviada</option>
                  {eligibleRfqs.map((item) => <option key={item.id} value={item.id}>v{item.version} · {item.subject}</option>)}
                </select>
              </label>
              <input type="file" accept=".pdf,.xlsx,.docx,application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
              <Button loading={busy} onClick={() => void upload()}><Upload className="h-4 w-4" /> Cargar y procesar</Button>
              <p className="text-xs text-text-secondary">La recepcion es manual. No se consulta inbox, Gmail ni Microsoft Graph.</p>
            </Card>

            <Card className="grid gap-2">
              <h3 className="font-semibold">Cotizaciones recibidas</h3>
              {quotes.length === 0 ? <p className="text-sm text-text-secondary">Aun no hay cotizaciones.</p> : quotes.map((quote) => (
                <button key={quote.id} type="button" className={`rounded-control border p-3 text-left ${selectedId === quote.id ? "border-brand-teal bg-teal-50" : "border-border-subtle bg-white"}`} onClick={() => void loadDetail(quote.id)}>
                  <div className="flex items-start justify-between gap-2"><span className="truncate text-sm font-medium">{quote.original_file_name}</span><StatusBadge value={quote.status} /></div>
                </button>
              ))}
            </Card>
          </div>

          <div className="grid content-start gap-4">
            {error ? <div className="rounded-panel border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900"><AlertTriangle className="mr-2 inline h-4 w-4" />{error}</div> : null}
            {!detail ? (
              <EmptyState icon={<FileSearch className="h-5 w-5" />} title="Selecciona una cotizacion" detail="Aqui aparecera la extraccion, evidencia y revision humana." />
            ) : (
              <>
                <Card className="grid gap-3">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div><h3 className="font-semibold">{detail.documents[0]?.original_file_name ?? "Cotizacion"}</h3><p className="text-sm text-text-secondary">Version {detail.version} · {detail.items.length} items · {detail.manual_edit_count} correcciones</p></div>
                    <StatusBadge value={detail.status} />
                  </div>
                  <div className="grid gap-2 text-sm sm:grid-cols-4">
                    <Metric label="Moneda" value={detail.currency ?? "Desconocida"} warning={!detail.currency} />
                    <Metric label="Total" value={detail.total_amount ?? "No encontrado"} warning={detail.total_amount == null} />
                    <Metric label="Entrega" value={detail.delivery_time_days == null ? "No encontrada" : `${detail.delivery_time_days} dias`} warning={detail.delivery_time_days == null} />
                    <Metric label="Task" value={processing?.task_status ?? detail.status} warning={processing?.task_status === "failed"} />
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {detail.status === "normalized" ? <Button onClick={() => void action(() => quoteApi.submitReview(detail.id, userId))}>Enviar a revision</Button> : null}
                    {detail.status === "pending_review" ? <Button onClick={() => void action(() => quoteApi.approve(detail.id, userId))}><Check className="h-4 w-4" /> Aprobar</Button> : null}
                    {!["approved", "rejected", "included_in_comparison"].includes(detail.status) ? <Button variant="secondary" onClick={() => void action(() => quoteApi.reprocess(detail.id, userId))}><RotateCcw className="h-4 w-4" /> Reprocess</Button> : null}
                    {!["approved", "rejected", "included_in_comparison"].includes(detail.status) ? <Button variant="secondary" onClick={() => { const reason = window.prompt("Motivo de rechazo"); if (reason) void action(() => quoteApi.reject(detail.id, userId, reason)); }}><X className="h-4 w-4" /> Rechazar</Button> : null}
                  </div>
                  {processing?.extraction_runs?.length ? <p className="text-xs text-text-secondary">Ultima extraccion: {processing.extraction_runs.at(-1)?.model} · prompt {processing.extraction_runs.at(-1)?.prompt_version} · tokens {processing.extraction_runs.at(-1)?.input_tokens}/{processing.extraction_runs.at(-1)?.output_tokens} · costo USD {processing.extraction_runs.at(-1)?.estimated_cost_usd}</p> : null}
                </Card>

                <div className="grid gap-4">
                  {detail.items.map((item) => <QuoteItemCard key={item.id} quote={detail} item={item} catalog={catalog} userId={userId} busy={busy} onSaved={(updated) => { setDetail(updated); void refreshQuotes(); }} onError={setError} />)}
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </Section>
  );
}

function QuoteItemCard({ quote, item, catalog, userId, busy, onSaved, onError }: { quote: QuoteDetail; item: QuoteItem; catalog: TenderCatalog | null; userId: UUID; busy: boolean; onSaved: (value: QuoteDetail) => void; onError: (value: string) => void }) {
  const [productId, setProductId] = useState(item.catalog_product_id ?? "");
  const [brand, setBrand] = useState(item.brand ?? "");
  const [model, setModel] = useState(item.model ?? "");
  const [quantity, setQuantity] = useState(item.quantity?.toString() ?? "");
  const [unit, setUnit] = useState(item.unit ?? "");
  const [unitPrice, setUnitPrice] = useState(item.unit_price?.toString() ?? "");
  const [totalPrice, setTotalPrice] = useState(item.total_price?.toString() ?? "");
  const [currency, setCurrency] = useState(item.currency ?? "");
  const [delivery, setDelivery] = useState(item.delivery_days?.toString() ?? "");
  const [compliance, setCompliance] = useState(item.compliance_status);
  const [notes, setNotes] = useState(item.notes ?? "");
  const requested = catalog?.products.find((product) => product.id === item.catalog_product_id);

  async function save() {
    try {
      const updated = await quoteApi.updateItem(quote.id, item.id, {
        changed_by_user_id: userId,
        catalog_product_id: productId || undefined,
        brand: brand || undefined,
        model: model || undefined,
        quantity: quantity ? Number(quantity) : undefined,
        unit: unit || undefined,
        unit_price: unitPrice ? Number(unitPrice) : undefined,
        total_price: totalPrice ? Number(totalPrice) : undefined,
        currency: currency || undefined,
        delivery_days: delivery ? Number(delivery) : undefined,
        compliance_status: compliance,
        notes: notes || undefined
      });
      onSaved(updated);
    } catch (cause) {
      onError(cause instanceof Error ? cause.message : "No fue posible guardar la correccion.");
    }
  }

  return (
    <Card className="grid gap-4">
      <div className="flex flex-wrap items-start justify-between gap-2"><div><h4 className="font-semibold">Cotizado: {item.product_name}</h4><p className="text-sm text-text-secondary">Solicitado: {requested?.name ?? "Sin coincidencia confirmada"}</p></div><div className="flex gap-2"><StatusBadge value={item.match_status} /><StatusBadge value={item.compliance_status} /><StatusBadge value={item.confidence_band} /></div></div>
      {item.warnings.length ? <div className="rounded-control border border-amber-300 bg-amber-50 p-3 text-sm"><strong>Revision requerida:</strong> {item.warnings.join(" · ")}</div> : null}
      <div className="grid gap-3 md:grid-cols-3">
        <label className="grid gap-1 text-sm"><span>Producto solicitado</span><select disabled={quote.status !== "pending_review"} className="h-10 rounded-control border border-border-subtle bg-white px-2" value={productId} onChange={(event) => setProductId(event.target.value)}><option value="">Sin identificar</option>{(catalog?.products ?? []).filter((p) => p.status === "approved").map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
        <Field label="Marca"><TextInput disabled={quote.status !== "pending_review"} value={brand} onChange={(e) => setBrand(e.target.value)} /></Field>
        <Field label="Modelo"><TextInput disabled={quote.status !== "pending_review"} value={model} onChange={(e) => setModel(e.target.value)} /></Field>
        <Field label="Cantidad"><TextInput disabled={quote.status !== "pending_review"} type="number" value={quantity} onChange={(e) => setQuantity(e.target.value)} /></Field>
        <Field label="Unidad"><TextInput disabled={quote.status !== "pending_review"} value={unit} onChange={(e) => setUnit(e.target.value)} /></Field>
        <Field label="Precio unitario"><TextInput disabled={quote.status !== "pending_review"} type="number" value={unitPrice} onChange={(e) => setUnitPrice(e.target.value)} placeholder="No encontrado" /></Field>
        <Field label="Precio total"><TextInput disabled={quote.status !== "pending_review"} type="number" value={totalPrice} onChange={(e) => setTotalPrice(e.target.value)} placeholder="No encontrado" /></Field>
        <Field label="Moneda"><TextInput disabled={quote.status !== "pending_review"} value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase())} placeholder="Desconocida" /></Field>
        <Field label="Entrega (dias)"><TextInput disabled={quote.status !== "pending_review"} type="number" value={delivery} onChange={(e) => setDelivery(e.target.value)} /></Field>
        <label className="grid gap-1 text-sm"><span>Cumplimiento</span><select disabled={quote.status !== "pending_review"} className="h-10 rounded-control border border-border-subtle bg-white px-2" value={compliance} onChange={(e) => setCompliance(e.target.value)}>{["unknown", "partial", "compliant", "non_compliant"].map((value) => <option key={value}>{value}</option>)}</select></label>
      </div>
      <Field label="Notas"><Textarea disabled={quote.status !== "pending_review"} value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
      <div className="rounded-control bg-slate-50 p-3 text-sm"><p className="font-medium">Evidencia</p>{item.evidence.length === 0 ? <p className="text-text-secondary">Sin evidencia trazable.</p> : item.evidence.map((evidence) => <div key={evidence.id} className="mt-2 border-l-2 border-brand-teal pl-2"><span className="text-xs font-medium">{evidence.field_name} · {evidence.location_type} {evidence.location_label} · {Math.round(evidence.confidence * 100)}%</span><p className="text-text-secondary">{evidence.fragment}</p></div>)}</div>
      {quote.status === "pending_review" ? <Button disabled={busy} onClick={() => void save()}>Guardar correccion</Button> : null}
    </Card>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) { return <label className="grid gap-1 text-sm"><span>{label}</span>{children}</label>; }
function Metric({ label, value, warning }: { label: string; value: string | number; warning?: boolean }) { return <div className={`rounded-control border p-3 ${warning ? "border-amber-300 bg-amber-50" : "border-border-subtle bg-slate-50"}`}><p className="text-xs text-text-secondary">{label}</p><p className="font-semibold">{String(value)}</p></div>; }
