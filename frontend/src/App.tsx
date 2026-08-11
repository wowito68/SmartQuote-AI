import { useEffect, useMemo, useState } from "react";

import { Layout, type ViewKey } from "./components/Layout";
import { Toast } from "./components/ui";
import { CatalogPanel } from "./features/catalog/CatalogPanel";
import { ComparisonPanel } from "./features/comparison/ComparisonPanel";
import { Dashboard } from "./features/dashboard/Dashboard";
import { DocumentsPanel } from "./features/documents/DocumentsPanel";
import { QuotesPanel } from "./features/quotes/QuotesPanel";
import { quoteApi } from "./features/quotes/api";
import type { Quote } from "./features/quotes/types";
import { RfqsPanel } from "./features/rfqs/RfqsPanel";
import { SuppliersPanel, type ManualSupplierForm } from "./features/suppliers/SuppliersPanel";
import { TenderWorkspace } from "./features/tenders/TenderWorkspace";
import { ApiError, api } from "./lib/api";
import type {
  Tender,
  TenderCatalog,
  TenderDocument,
  TenderRfqs,
  TenderSuppliers,
  UUID
} from "./lib/types";

const DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000001";
const views = [
  "dashboard",
  "tenders",
  "documents",
  "catalog",
  "suppliers",
  "rfqs",
  "quotes",
  "comparison"
] as const;

function getInitialView(): ViewKey {
  const hash = window.location.hash.replace("#", "");
  return views.includes(hash as ViewKey) ? (hash as ViewKey) : "dashboard";
}

export function App() {
  const [activeView, setActiveViewState] = useState<ViewKey>(getInitialView);
  const [userId, setUserId] = useState(
    () => window.localStorage.getItem("smartquote:user_id") ?? DEFAULT_USER_ID
  );
  const [health, setHealth] = useState<{
    status: string;
    project_name: string;
    version: string;
    environment: string;
  } | null>(null);
  const [tenders, setTenders] = useState<Tender[]>([]);
  const [selectedTenderId, setSelectedTenderId] = useState<UUID | null>(null);
  const [documents, setDocuments] = useState<TenderDocument[]>([]);
  const [catalog, setCatalog] = useState<TenderCatalog | null>(null);
  const [suppliers, setSuppliers] = useState<TenderSuppliers | null>(null);
  const [rfqs, setRfqs] = useState<TenderRfqs | null>(null);
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [loadingTenders, setLoadingTenders] = useState(false);
  const [loadingDocuments, setLoadingDocuments] = useState(false);
  const [loadingCatalog, setLoadingCatalog] = useState(false);
  const [loadingSuppliers, setLoadingSuppliers] = useState(false);
  const [loadingRfqs, setLoadingRfqs] = useState(false);
  const [loadingQuotes, setLoadingQuotes] = useState(false);
  const [toast, setToast] = useState<{ message: string; tone: "info" | "error" } | null>(null);

  const selectedTender = useMemo(
    () => tenders.find((tender) => tender.id === selectedTenderId) ?? null,
    [selectedTenderId, tenders]
  );

  useEffect(() => {
    window.localStorage.setItem("smartquote:user_id", userId);
  }, [userId]);

  useEffect(() => {
    void bootstrap();
  }, []);

  useEffect(() => {
    const onHashChange = () => setActiveViewState(getInitialView());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  useEffect(() => {
    if (!selectedTenderId) {
      setDocuments([]);
      setCatalog(null);
      setSuppliers(null);
      setRfqs(null);
      setQuotes([]);
      return;
    }
    void refreshTenderWorkspace(selectedTenderId);
  }, [selectedTenderId]);

  function setActiveView(view: ViewKey) {
    setActiveViewState(view);
    window.history.replaceState(null, "", `#${view}`);
  }

  async function bootstrap() {
    await Promise.all([loadHealth(), loadTenders()]);
  }

  async function loadHealth() {
    try {
      setHealth(await api.health());
    } catch (error) {
      reportError(error);
    }
  }

  async function loadTenders() {
    setLoadingTenders(true);
    try {
      const response = await api.listTenders();
      setTenders(response.items);
      setSelectedTenderId((current) => current ?? response.items[0]?.id ?? null);
    } catch (error) {
      reportError(error);
    } finally {
      setLoadingTenders(false);
    }
  }

  async function refreshTenderWorkspace(tenderId = selectedTenderId) {
    if (!tenderId) return;
    await Promise.all([
      loadDocuments(tenderId),
      loadCatalog(tenderId),
      loadSuppliers(tenderId),
      loadRfqs(tenderId),
      loadQuotes(tenderId)
    ]);
  }

  async function loadDocuments(tenderId = selectedTenderId) {
    if (!tenderId) return;
    setLoadingDocuments(true);
    try {
      setDocuments((await api.listDocuments(tenderId)).items);
    } catch (error) {
      handleOptionalResource(error, () => setDocuments([]));
    } finally {
      setLoadingDocuments(false);
    }
  }

  async function loadCatalog(tenderId = selectedTenderId) {
    if (!tenderId) return;
    setLoadingCatalog(true);
    try {
      setCatalog(await api.getCatalog(tenderId));
    } catch (error) {
      handleOptionalResource(error, () => setCatalog(null));
    } finally {
      setLoadingCatalog(false);
    }
  }

  async function loadSuppliers(tenderId = selectedTenderId) {
    if (!tenderId) return;
    setLoadingSuppliers(true);
    try {
      setSuppliers(await api.listSuppliers(tenderId));
    } catch (error) {
      handleOptionalResource(error, () => setSuppliers(null));
    } finally {
      setLoadingSuppliers(false);
    }
  }

  async function loadRfqs(tenderId = selectedTenderId) {
    if (!tenderId) return;
    setLoadingRfqs(true);
    try {
      setRfqs(await api.listRfqs(tenderId));
    } catch (error) {
      handleOptionalResource(error, () => setRfqs(null));
    } finally {
      setLoadingRfqs(false);
    }
  }

  async function loadQuotes(tenderId = selectedTenderId) {
    if (!tenderId) return;
    setLoadingQuotes(true);
    try {
      setQuotes((await quoteApi.list(tenderId)).items);
    } catch (error) {
      handleOptionalResource(error, () => setQuotes([]));
    } finally {
      setLoadingQuotes(false);
    }
  }

  async function createTender(payload: {
    title: string;
    description: string | null;
    deadline: string | null;
    created_by_user_id: UUID;
  }) {
    try {
      const created = await api.createTender(payload);
      setTenders((current) => [created, ...current]);
      setSelectedTenderId(created.id);
      setToast({ message: "Licitacion creada.", tone: "info" });
    } catch (error) {
      reportError(error);
    }
  }

  async function archiveTender(tenderId: UUID) {
    try {
      await api.archiveTender(tenderId);
      setTenders((current) => current.filter((tender) => tender.id !== tenderId));
      setSelectedTenderId(null);
      setToast({ message: "Licitacion archivada.", tone: "info" });
    } catch (error) {
      reportError(error);
    }
  }

  async function uploadDocuments(files: FileList) {
    if (!selectedTenderId) return;
    try {
      setDocuments((await api.uploadDocuments(selectedTenderId, userId, files)).items);
      setToast({ message: "Documentos cargados y encolados.", tone: "info" });
    } catch (error) {
      reportError(error);
    }
  }

  async function deleteDocument(documentId: UUID) {
    try {
      await api.deleteDocument(documentId, userId);
      await loadDocuments();
      setToast({ message: "Documento eliminado.", tone: "info" });
    } catch (error) {
      reportError(error);
    }
  }

  async function extractCatalog() {
    if (!selectedTenderId) return;
    try {
      await api.requestCatalogExtraction(selectedTenderId);
      setToast({ message: "Extraccion de catalogo encolada.", tone: "info" });
      await loadCatalog(selectedTenderId);
    } catch (error) {
      reportError(error);
    }
  }

  async function approveProduct(productId: UUID) {
    try {
      await api.approveProduct(productId, userId);
      await loadCatalog();
      setToast({ message: "Producto aprobado.", tone: "info" });
    } catch (error) {
      reportError(error);
    }
  }

  async function rejectProduct(productId: UUID, reason: string) {
    try {
      await api.rejectProduct(productId, userId, reason);
      await loadCatalog();
      setToast({ message: "Producto rechazado.", tone: "info" });
    } catch (error) {
      reportError(error);
    }
  }

  async function approveCatalog() {
    if (!selectedTenderId) return;
    try {
      await api.approveCatalog(selectedTenderId, userId);
      await loadCatalog(selectedTenderId);
      setToast({ message: "Catalogo aprobado.", tone: "info" });
    } catch (error) {
      reportError(error);
    }
  }

  async function discoverSuppliers() {
    if (!selectedTenderId) return;
    try {
      await api.discoverSuppliers(selectedTenderId, userId);
      setToast({ message: "Busqueda de proveedores encolada.", tone: "info" });
      await loadSuppliers(selectedTenderId);
    } catch (error) {
      reportError(error);
    }
  }

  async function createManualSupplier(form: ManualSupplierForm) {
    if (!selectedTenderId) return;
    const contacts = [
      form.email.trim()
        ? {
            contact_type: "email",
            value: form.email.trim(),
            confidence: 1,
            source_url: `manual://user/${userId}`,
            contact_name: null,
            role: null
          }
        : null,
      form.phone.trim()
        ? {
            contact_type: "phone",
            value: form.phone.trim(),
            confidence: 1,
            source_url: `manual://user/${userId}`,
            contact_name: null,
            role: null
          }
        : null
    ].filter(Boolean) as Array<{
      contact_type: string;
      value: string;
      confidence: number;
      source_url: string;
      contact_name: string | null;
      role: string | null;
    }>;
    try {
      await api.createManualSupplier({
        tender_id: selectedTenderId,
        created_by_user_id: userId,
        legal_name: form.legalName.trim() || null,
        trade_name: form.tradeName.trim() || null,
        website: form.website.trim() || null,
        category: form.category.trim() || null,
        country: form.country.trim() || null,
        city: form.city.trim() || null,
        description: null,
        contacts,
        source_note: "Alta manual desde dashboard"
      });
      await loadSuppliers(selectedTenderId);
      setToast({ message: "Proveedor agregado.", tone: "info" });
    } catch (error) {
      reportError(error);
    }
  }

  async function approveSupplier(supplierId: UUID) {
    try {
      await api.approveSupplier(supplierId, userId);
      await loadSuppliers();
      setToast({ message: "Proveedor aprobado.", tone: "info" });
    } catch (error) {
      reportError(error);
    }
  }

  async function rejectSupplier(supplierId: UUID, reason: string) {
    try {
      await api.rejectSupplier(supplierId, userId, reason);
      await loadSuppliers();
      setToast({ message: "Proveedor rechazado.", tone: "info" });
    } catch (error) {
      reportError(error);
    }
  }

  async function generateRfqs(deadline: string, observations: string | null, documentIds: UUID[]) {
    if (!selectedTenderId) return;
    try {
      await api.generateRfqs(selectedTenderId, {
        generated_by_user_id: userId,
        response_deadline: deadline,
        observations,
        document_ids: documentIds.length ? documentIds : null
      });
      await loadRfqs(selectedTenderId);
      setToast({ message: "RFQs generadas.", tone: "info" });
    } catch (error) {
      reportError(error);
    }
  }

  async function approveRfq(rfqId: UUID) {
    try {
      await api.approveRfq(rfqId, userId);
      await loadRfqs();
      setToast({ message: "RFQ aprobada.", tone: "info" });
    } catch (error) {
      reportError(error);
    }
  }

  async function sendRfq(rfqId: UUID) {
    try {
      await api.sendRfq(rfqId, userId);
      await loadRfqs();
      setToast({ message: "RFQ encolada para envio.", tone: "info" });
    } catch (error) {
      reportError(error);
    }
  }

  function handleOptionalResource(error: unknown, clear: () => void) {
    if (error instanceof ApiError && error.status === 404) {
      clear();
      return;
    }
    reportError(error);
  }

  function reportError(error: unknown) {
    const message = error instanceof Error ? error.message : "Ocurrio un error inesperado.";
    setToast({ message, tone: "error" });
  }

  const rfqsPanel = (
    <RfqsPanel
      tenderId={selectedTender?.id ?? null}
      userId={userId}
      documents={documents}
      rfqs={rfqs}
      loading={loadingRfqs}
      onRefresh={() => loadRfqs()}
      onGenerate={generateRfqs}
      onApprove={approveRfq}
      onSend={sendRfq}
    />
  );

  const content =
    activeView === "dashboard" ? (
      <Dashboard tenders={tenders} health={health} catalog={catalog} suppliers={suppliers} rfqs={rfqs} />
    ) : activeView === "tenders" ? (
      <TenderWorkspace
        tenders={tenders}
        selectedTenderId={selectedTenderId}
        userId={userId}
        loading={loadingTenders}
        documents={documents}
        catalog={catalog}
        suppliers={suppliers}
        rfqs={rfqs}
        documentsPanel={
          <DocumentsPanel
            tenderId={selectedTender?.id ?? null}
            userId={userId}
            documents={documents}
            loading={loadingDocuments}
            onUpload={uploadDocuments}
            onDelete={deleteDocument}
            onRefresh={() => loadDocuments()}
            onExtractCatalog={extractCatalog}
          />
        }
        catalogPanel={
          <CatalogPanel
            tenderId={selectedTender?.id ?? null}
            catalog={catalog}
            loading={loadingCatalog}
            onRefresh={() => loadCatalog()}
            onApproveProduct={approveProduct}
            onRejectProduct={rejectProduct}
            onApproveCatalog={approveCatalog}
          />
        }
        suppliersPanel={
          <SuppliersPanel
            tenderId={selectedTender?.id ?? null}
            userId={userId}
            suppliers={suppliers}
            loading={loadingSuppliers}
            onRefresh={() => loadSuppliers()}
            onDiscover={discoverSuppliers}
            onCreateManual={createManualSupplier}
            onApprove={approveSupplier}
            onReject={rejectSupplier}
          />
        }
        rfqsPanel={rfqsPanel}
        onSelectTender={setSelectedTenderId}
        onCreateTender={createTender}
        onArchiveTender={archiveTender}
        onRefresh={loadTenders}
      />
    ) : activeView === "documents" ? (
      <DocumentsPanel
        tenderId={selectedTender?.id ?? null}
        userId={userId}
        documents={documents}
        loading={loadingDocuments}
        onUpload={uploadDocuments}
        onDelete={deleteDocument}
        onRefresh={() => loadDocuments()}
        onExtractCatalog={extractCatalog}
      />
    ) : activeView === "catalog" ? (
      <CatalogPanel
        tenderId={selectedTender?.id ?? null}
        catalog={catalog}
        loading={loadingCatalog}
        onRefresh={() => loadCatalog()}
        onApproveProduct={approveProduct}
        onRejectProduct={rejectProduct}
        onApproveCatalog={approveCatalog}
      />
    ) : activeView === "suppliers" ? (
      <SuppliersPanel
        tenderId={selectedTender?.id ?? null}
        userId={userId}
        suppliers={suppliers}
        loading={loadingSuppliers}
        onRefresh={() => loadSuppliers()}
        onDiscover={discoverSuppliers}
        onCreateManual={createManualSupplier}
        onApprove={approveSupplier}
        onReject={rejectSupplier}
      />
    ) : activeView === "rfqs" ? (
      rfqsPanel
    ) : activeView === "quotes" ? (
      <QuotesPanel
        tenderId={selectedTender?.id ?? null}
        userId={userId}
        suppliers={suppliers}
        rfqs={rfqs}
        catalogProducts={catalog?.products ?? []}
        quotes={quotes}
        loading={loadingQuotes}
        onRefresh={() => loadQuotes()}
        onError={reportError}
      />
    ) : activeView === "comparison" ? (
      <ComparisonPanel
        tenderId={selectedTender?.id ?? null}
        userId={userId}
        onTenderChanged={loadTenders}
        onError={reportError}
      />
    ) : null;

  return (
    <Layout
      activeView={activeView}
      onViewChange={setActiveView}
      userId={userId}
      onUserIdChange={setUserId}
      healthStatus={health?.status ?? "offline"}
      selectedTenderTitle={selectedTender?.title ?? null}
      onRefresh={() => void bootstrap()}
    >
      {content}
      {toast ? <Toast message={toast.message} tone={toast.tone} /> : null}
    </Layout>
  );
}
