import type { ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Info, Loader2, X } from "lucide-react";

type Tone = "neutral" | "success" | "warning" | "danger" | "info";

export const inputClass =
  "min-h-11 w-full rounded-control border border-border-subtle bg-white px-3 text-sm text-text-primary shadow-sm transition placeholder:text-text-muted hover:border-border-strong focus:border-brand-teal disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-text-muted";

export function Button({
  children,
  type = "button",
  variant = "primary",
  size = "md",
  disabled = false,
  loading = false,
  onClick,
  title
}: {
  children: ReactNode;
  type?: "button" | "submit";
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md";
  disabled?: boolean;
  loading?: boolean;
  onClick?: () => void;
  title?: string;
}) {
  const styles = {
    primary: "border-brand-teal bg-brand-teal text-white hover:bg-brand-tealDark",
    secondary:
      "border-border-subtle bg-white text-text-primary hover:border-border-strong hover:bg-slate-50",
    ghost: "border-transparent bg-transparent text-text-secondary hover:bg-slate-100",
    danger: "border-semantic-danger bg-semantic-danger text-white hover:bg-rose-800"
  };
  const sizes = {
    sm: "min-h-9 px-2.5 text-xs",
    md: "min-h-11 px-4 text-sm"
  };

  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-control border font-medium shadow-sm transition disabled:cursor-not-allowed disabled:opacity-50 ${styles[variant]} ${sizes[size]}`}
      type={type}
      disabled={disabled || loading}
      onClick={onClick}
      title={title}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : null}
      {children}
    </button>
  );
}

export function IconButton({
  children,
  label,
  disabled = false,
  active = false,
  onClick
}: {
  children: ReactNode;
  label: string;
  disabled?: boolean;
  active?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      className={`inline-flex h-10 w-10 items-center justify-center rounded-control border text-slate-700 shadow-sm transition disabled:cursor-not-allowed disabled:opacity-50 ${
        active
          ? "border-brand-teal bg-brand-teal text-white"
          : "border-border-subtle bg-white hover:bg-slate-50"
      }`}
      type="button"
      title={label}
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

export function Card({
  children,
  className = "",
  padding = "md"
}: {
  children: ReactNode;
  className?: string;
  padding?: "none" | "sm" | "md";
}) {
  const paddingClass = padding === "none" ? "" : padding === "sm" ? "p-4" : "p-5";
  return (
    <div
      className={`rounded-panel border border-border-subtle bg-surface-base shadow-panel ${paddingClass} ${className}`}
    >
      {children}
    </div>
  );
}

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: Tone }) {
  const styles = {
    neutral: "border-slate-200 bg-slate-50 text-slate-700",
    success: "border-emerald-200 bg-semantic-successBg text-semantic-success",
    warning: "border-amber-200 bg-semantic-warningBg text-semantic-warning",
    danger: "border-rose-200 bg-semantic-dangerBg text-semantic-danger",
    info: "border-blue-200 bg-semantic-infoBg text-semantic-info"
  };
  return (
    <span
      className={`inline-flex max-w-full items-center rounded-full border px-2.5 py-1 text-xs font-medium ${styles[tone]}`}
    >
      <span className="truncate">{children}</span>
    </span>
  );
}

export function StatusBadge({ value }: { value: string }) {
  const normalized = value.toLowerCase();
  const tone: Tone =
    normalized.includes("approved") ||
    normalized.includes("sent") ||
    normalized.includes("ready") ||
    normalized.includes("processed") ||
    normalized.includes("text_extracted")
      ? "success"
      : normalized.includes("failed") ||
          normalized.includes("rejected") ||
          normalized.includes("cancelled") ||
          normalized.includes("archived")
        ? "danger"
        : normalized.includes("pending") ||
            normalized.includes("draft") ||
            normalized.includes("review") ||
            normalized.includes("queued") ||
            normalized.includes("processing") ||
            normalized.includes("needs_ocr")
          ? "warning"
          : "info";

  return <Badge tone={tone}>{humanize(value)}</Badge>;
}

export function Section({
  title,
  eyebrow,
  action,
  children,
  description
}: {
  title: string;
  eyebrow?: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="grid gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          {eyebrow ? (
            <p className="mb-1 text-xs font-semibold uppercase tracking-normal text-brand-teal">
              {eyebrow}
            </p>
          ) : null}
          <h2 className="text-lg font-semibold text-text-primary">{title}</h2>
          {description ? <p className="mt-1 text-sm text-text-secondary">{description}</p> : null}
        </div>
        {action ? <div className="flex shrink-0 flex-wrap gap-2">{action}</div> : null}
      </div>
      {children}
    </section>
  );
}

export function EmptyState({
  title,
  detail,
  action,
  icon
}: {
  title: string;
  detail: string;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <Card className="flex flex-col items-start gap-3 border-dashed bg-surface-muted">
      <div className="flex h-11 w-11 items-center justify-center rounded-panel bg-brand-tealSoft text-brand-teal">
        {icon ?? <Info className="h-5 w-5" aria-hidden />}
      </div>
      <div>
        <p className="font-semibold text-text-primary">{title}</p>
        <p className="mt-1 max-w-xl text-sm leading-6 text-text-secondary">{detail}</p>
      </div>
      {action}
    </Card>
  );
}

export function LoadingState({ label = "Cargando informacion" }: { label?: string }) {
  return (
    <div className="flex min-h-40 items-center justify-center rounded-panel border border-border-subtle bg-white">
      <div className="flex items-center gap-3 text-sm text-text-secondary">
        <Loader2 className="h-5 w-5 animate-spin text-brand-teal" aria-hidden />
        {label}
      </div>
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-slate-200 ${className}`} />;
}

export function Alert({
  title,
  detail,
  tone = "info"
}: {
  title: string;
  detail?: string;
  tone?: Exclude<Tone, "neutral">;
}) {
  const icon = {
    info: <Info className="h-5 w-5" aria-hidden />,
    success: <CheckCircle2 className="h-5 w-5" aria-hidden />,
    warning: <AlertTriangle className="h-5 w-5" aria-hidden />,
    danger: <AlertTriangle className="h-5 w-5" aria-hidden />
  };
  const styles = {
    info: "border-blue-200 bg-semantic-infoBg text-semantic-info",
    success: "border-emerald-200 bg-semantic-successBg text-semantic-success",
    warning: "border-amber-200 bg-semantic-warningBg text-semantic-warning",
    danger: "border-rose-200 bg-semantic-dangerBg text-semantic-danger"
  };
  return (
    <div className={`flex gap-3 rounded-panel border p-4 ${styles[tone]}`} role="status">
      <div className="shrink-0">{icon[tone]}</div>
      <div>
        <p className="text-sm font-semibold">{title}</p>
        {detail ? <p className="mt-1 text-sm opacity-90">{detail}</p> : null}
      </div>
    </div>
  );
}

export function Field({
  label,
  children,
  hint,
  error
}: {
  label: string;
  children: ReactNode;
  hint?: string;
  error?: string;
}) {
  return (
    <label className="grid gap-1.5 text-sm">
      <span className="font-medium text-slate-700">{label}</span>
      {children}
      {error ? (
        <span className="text-xs font-medium text-semantic-danger">{error}</span>
      ) : hint ? (
        <span className="text-xs text-text-secondary">{hint}</span>
      ) : null}
    </label>
  );
}

export function TextInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${inputClass} ${props.className ?? ""}`} />;
}

export function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={`${inputClass} min-h-28 resize-y py-2 ${props.className ?? ""}`}
    />
  );
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={`${inputClass} ${props.className ?? ""}`} />;
}

export function Tabs<T extends string>({
  tabs,
  active,
  onChange
}: {
  tabs: Array<{ key: T; label: string; count?: number }>;
  active: T;
  onChange: (value: T) => void;
}) {
  return (
    <div className="flex gap-1 overflow-x-auto rounded-panel border border-border-subtle bg-slate-100 p-1">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          className={`inline-flex min-h-10 shrink-0 items-center gap-2 rounded-md px-3 text-sm font-medium transition ${
            active === tab.key
              ? "bg-white text-text-primary shadow-sm"
              : "text-text-secondary hover:bg-white/70 hover:text-text-primary"
          }`}
          type="button"
          onClick={() => onChange(tab.key)}
        >
          {tab.label}
          {tab.count !== undefined ? <Badge>{tab.count}</Badge> : null}
        </button>
      ))}
    </div>
  );
}

export function Modal({
  open,
  title,
  description,
  children,
  footer,
  onClose
}: {
  open: boolean;
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
  onClose: () => void;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/45 p-3 sm:items-center">
      <div
        className="max-h-[92vh] w-full max-w-2xl overflow-hidden rounded-panel bg-white shadow-floating"
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
      >
        <div className="flex items-start justify-between gap-4 border-b border-border-subtle px-5 py-4">
          <div>
            <h2 id="modal-title" className="text-lg font-semibold text-text-primary">
              {title}
            </h2>
            {description ? <p className="mt-1 text-sm text-text-secondary">{description}</p> : null}
          </div>
          <IconButton label="Cerrar" onClick={onClose}>
            <X className="h-4 w-4" />
          </IconButton>
        </div>
        <div className="max-h-[62vh] overflow-y-auto px-5 py-5">{children}</div>
        {footer ? (
          <div className="flex flex-col-reverse gap-2 border-t border-border-subtle bg-slate-50 px-5 py-4 sm:flex-row sm:justify-end">
            {footer}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function ConfirmationDialog({
  open,
  title,
  detail,
  confirmLabel,
  loading = false,
  onCancel,
  onConfirm
}: {
  open: boolean;
  title: string;
  detail: string;
  confirmLabel: string;
  loading?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <Modal
      open={open}
      title={title}
      description={detail}
      onClose={onCancel}
      footer={
        <>
          <Button variant="secondary" onClick={onCancel}>
            Cancelar
          </Button>
          <Button variant="danger" loading={loading} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <Alert tone="warning" title="Esta accion requiere confirmacion" />
    </Modal>
  );
}

export function DataTable({
  headers,
  children
}: {
  headers: string[];
  children: ReactNode;
}) {
  return (
    <div className="overflow-hidden rounded-panel border border-border-subtle bg-white">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] border-collapse text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-normal text-text-secondary">
            <tr>
              {headers.map((header) => (
                <th key={header} className="px-4 py-3 font-semibold">
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border-subtle">{children}</tbody>
        </table>
      </div>
    </div>
  );
}

export function Pagination({
  page,
  totalPages,
  onPageChange
}: {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-3 text-sm text-text-secondary">
      <span>
        Pagina {page} de {Math.max(totalPages, 1)}
      </span>
      <div className="flex gap-2">
        <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
          Anterior
        </Button>
        <Button
          size="sm"
          variant="secondary"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
        >
          Siguiente
        </Button>
      </div>
    </div>
  );
}

export function Tooltip({ text, children }: { text: string; children: ReactNode }) {
  return (
    <span className="group relative inline-flex">
      {children}
      <span className="pointer-events-none absolute bottom-full left-1/2 z-40 mb-2 hidden max-w-xs -translate-x-1/2 rounded-md bg-slate-900 px-2 py-1 text-xs text-white shadow-floating group-hover:block group-focus-within:block">
        {text}
      </span>
    </span>
  );
}

export function Toast({ message, tone = "info" }: { message: string; tone?: "info" | "error" }) {
  return (
    <div
      className={`fixed bottom-4 right-4 z-50 max-w-md rounded-panel border px-4 py-3 text-sm shadow-floating ${
        tone === "error"
          ? "border-rose-200 bg-semantic-dangerBg text-semantic-danger"
          : "border-teal-200 bg-white text-text-primary"
      }`}
      role="status"
    >
      {message}
    </div>
  );
}

export function humanize(value: string): string {
  return value.split("_").join(" ");
}

