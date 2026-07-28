import { Download, FileText, FileUp, RefreshCcw, Trash2, UploadCloud, Zap } from "lucide-react";
import { useState } from "react";

import {
  Button,
  DataTable,
  EmptyState,
  Section,
  StatusBadge
} from "../../components/ui";
import { formatBytes, formatDate } from "../../lib/format";
import type { TenderDocument, UUID } from "../../lib/types";

export function DocumentsPanel({
  tenderId,
  userId,
  documents,
  loading,
  onUpload,
  onDelete,
  onRefresh,
  onExtractCatalog
}: {
  tenderId: UUID | null;
  userId: UUID;
  documents: TenderDocument[];
  loading: boolean;
  onUpload: (files: FileList) => Promise<void>;
  onDelete: (documentId: UUID) => Promise<void>;
  onRefresh: () => Promise<void>;
  onExtractCatalog: () => Promise<void>;
}) {
  const [files, setFiles] = useState<FileList | null>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [deletingId, setDeletingId] = useState<UUID | null>(null);

  async function upload() {
    if (!files) return;
    setUploading(true);
    try {
      await onUpload(files);
      setFiles(null);
    } finally {
      setUploading(false);
    }
  }

  async function extractCatalog() {
    setExtracting(true);
    try {
      await onExtractCatalog();
    } finally {
      setExtracting(false);
    }
  }

  async function deleteDocument(documentId: UUID) {
    setDeletingId(documentId);
    try {
      await onDelete(documentId);
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <Section
      title="Documentos"
      eyebrow="Recepcion y procesamiento"
      description="Carga PDFs privados, consulta su estado y dispara la extraccion del catalogo."
      action={
        <>
          <Button variant="secondary" onClick={() => void onRefresh()}>
            <RefreshCcw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            Refrescar
          </Button>
          <Button
            disabled={!tenderId || documents.length === 0}
            loading={extracting}
            onClick={() => void extractCatalog()}
          >
            <Zap className="h-4 w-4" />
            Extraer catalogo
          </Button>
        </>
      }
    >
      {!tenderId ? (
        <EmptyState title="Sin licitacion seleccionada" detail="Selecciona una licitacion." />
      ) : (
        <div className="grid gap-5">
          <label
            className={`grid min-h-44 cursor-pointer place-items-center rounded-panel border border-dashed bg-surface-muted p-6 text-center transition ${
              dragging ? "border-brand-teal bg-brand-tealSoft" : "border-border-strong"
            }`}
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              setFiles(event.dataTransfer.files);
            }}
          >
            <input
              className="sr-only"
              type="file"
              accept="application/pdf"
              multiple
              onChange={(event) => setFiles(event.target.files)}
            />
            <div className="grid justify-items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-panel bg-brand-teal text-white">
                <UploadCloud className="h-6 w-6" aria-hidden />
              </div>
              <div>
                <p className="font-semibold text-text-primary">
                  Arrastra PDFs o selecciona archivos
                </p>
                <p className="mt-1 text-sm text-text-secondary">
                  {files?.length ? `${files.length} archivo(s) listos para subir` : "PDF · hasta el limite configurado por el backend"}
                </p>
              </div>
              <Button disabled={!files || !userId} loading={uploading} onClick={() => void upload()}>
                <FileUp className="h-4 w-4" />
                Subir documentos
              </Button>
            </div>
          </label>

          {documents.length === 0 ? (
            <EmptyState
              icon={<FileText className="h-5 w-5" />}
              title="No hay documentos"
              detail="Carga los PDFs de la licitacion para iniciar validacion, extraccion de texto y catalogo."
            />
          ) : (
            <>
              <div className="hidden lg:block">
                <DataTable headers={["Documento", "Estado", "Tamano", "Subido", "Acciones"]}>
                  {documents.map((document) => (
                    <tr key={document.id} className="hover:bg-slate-50">
                      <td className="max-w-[420px] px-4 py-3">
                        <p className="truncate font-semibold text-text-primary">
                          {document.original_file_name}
                        </p>
                        <p className="mt-1 truncate text-xs text-text-secondary">
                          {document.file_hash}
                        </p>
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge value={document.status} />
                      </td>
                      <td className="px-4 py-3 text-text-secondary">
                        {formatBytes(document.file_size)}
                      </td>
                      <td className="px-4 py-3 text-text-secondary">
                        {formatDate(document.uploaded_at)}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex gap-2">
                          <a
                            className="inline-flex min-h-9 items-center justify-center gap-2 rounded-control border border-border-subtle bg-white px-3 text-xs font-medium text-text-primary shadow-sm transition hover:bg-slate-50"
                            href={`/api/v1/documents/${document.id}/download`}
                          >
                            <Download className="h-4 w-4" />
                            Descargar
                          </a>
                          <Button
                            size="sm"
                            variant="ghost"
                            loading={deletingId === document.id}
                            onClick={() => void deleteDocument(document.id)}
                          >
                            <Trash2 className="h-4 w-4" />
                            Eliminar
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </DataTable>
              </div>
              <div className="grid gap-3 lg:hidden">
                {documents.map((document) => (
                  <div key={document.id} className="rounded-panel border border-border-subtle bg-white p-4 shadow-panel">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate font-semibold text-text-primary">
                          {document.original_file_name}
                        </p>
                        <p className="mt-1 text-sm text-text-secondary">
                          {formatBytes(document.file_size)} · {formatDate(document.uploaded_at)}
                        </p>
                      </div>
                      <StatusBadge value={document.status} />
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </Section>
  );
}

