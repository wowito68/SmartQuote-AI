import {
  BarChart3,
  Boxes,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  FileText,
  Handshake,
  Mail,
  Menu,
  ReceiptText,
  RefreshCcw,
  Settings2,
  X
} from "lucide-react";
import type { ReactNode } from "react";
import { useState } from "react";

import { IconButton, StatusBadge, Tooltip } from "./ui";

export type ViewKey = "dashboard" | "tenders" | "documents" | "catalog" | "suppliers" | "rfqs" | "quotes";

const navItems: Array<{ key: ViewKey; label: string; icon: ReactNode }> = [
  { key: "dashboard", label: "Tablero", icon: <BarChart3 className="h-4 w-4" /> },
  { key: "tenders", label: "Licitaciones", icon: <ClipboardList className="h-4 w-4" /> },
  { key: "documents", label: "Documentos", icon: <FileText className="h-4 w-4" /> },
  { key: "catalog", label: "Catalogo", icon: <Boxes className="h-4 w-4" /> },
  { key: "suppliers", label: "Proveedores", icon: <Handshake className="h-4 w-4" /> },
  { key: "rfqs", label: "RFQs", icon: <Mail className="h-4 w-4" /> },
  { key: "quotes", label: "Cotizaciones", icon: <ReceiptText className="h-4 w-4" /> }
];

const pageCopy: Record<ViewKey, { title: string; description: string }> = {
  dashboard: { title: "Tablero", description: "Estado general del flujo de compras y servicios conectados." },
  tenders: { title: "Licitaciones", description: "Gestiona oportunidades, revisa avance y coordina cada etapa." },
  documents: { title: "Documentos", description: "Carga PDFs, consulta estado y prepara documentos para IA." },
  catalog: { title: "Catalogo", description: "Revisa productos extraidos, confianza y aprobaciones." },
  suppliers: { title: "Proveedores", description: "Administra candidatos, contactos y aprobaciones." },
  rfqs: { title: "RFQs", description: "Genera, aprueba y envia solicitudes de cotizacion." },
  quotes: { title: "Cotizaciones", description: "Recibe cotizaciones manualmente, revisa evidencia y aprueba datos comparables." }
};

export function Layout({ activeView, onViewChange, userId, onUserIdChange, healthStatus, selectedTenderTitle, onRefresh, children }: {
  activeView: ViewKey; onViewChange: (view: ViewKey) => void; userId: string; onUserIdChange: (value: string) => void; healthStatus: string; selectedTenderTitle?: string | null; onRefresh: () => void; children: ReactNode;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const copy = pageCopy[activeView];
  function changeView(view: ViewKey) { onViewChange(view); setMobileOpen(false); }
  return (
    <div className="min-h-screen bg-surface-app text-text-primary">
      <Sidebar activeView={activeView} collapsed={collapsed} userId={userId} onUserIdChange={onUserIdChange} onToggle={() => setCollapsed((value) => !value)} onViewChange={changeView} />
      <div className={`min-h-screen transition-[padding] duration-200 ${collapsed ? "lg:pl-20" : "lg:pl-sidebar"}`}>
        <header className="sticky top-0 z-30 border-b border-border-subtle bg-white/95 backdrop-blur">
          <div className="mx-auto flex max-w-[1540px] flex-col gap-3 px-4 py-3 sm:px-6 xl:px-8">
            <div className="flex items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-3">
                <IconButton label="Abrir navegacion" onClick={() => setMobileOpen(true)}><Menu className="h-4 w-4" /></IconButton>
                <div className="min-w-0"><div className="flex items-center gap-2 text-xs text-text-secondary"><span>SmartQuote AI</span><span>/</span><span className="truncate">{copy.title}</span>{selectedTenderTitle ? <><span className="hidden sm:inline">/</span><span className="hidden max-w-[320px] truncate sm:inline">{selectedTenderTitle}</span></> : null}</div><h1 className="truncate text-lg font-semibold text-text-primary sm:text-xl">{copy.title}</h1></div>
              </div>
              <div className="flex shrink-0 items-center gap-2"><div className="hidden sm:block"><StatusBadge value={healthStatus} /></div><IconButton label="Actualizar datos" onClick={onRefresh}><RefreshCcw className="h-4 w-4" /></IconButton></div>
            </div><p className="text-sm text-text-secondary">{copy.description}</p>
          </div>
        </header>
        <main className="mx-auto max-w-[1540px] px-4 py-5 sm:px-6 xl:px-8">{children}</main>
      </div>
      {mobileOpen ? <div className="fixed inset-0 z-50 lg:hidden"><button className="absolute inset-0 bg-slate-950/50" type="button" aria-label="Cerrar navegacion" onClick={() => setMobileOpen(false)} /><div className="absolute inset-y-0 left-0 w-[86vw] max-w-80 bg-brand-navy shadow-floating"><MobileSidebar activeView={activeView} userId={userId} onUserIdChange={onUserIdChange} onClose={() => setMobileOpen(false)} onViewChange={changeView} /></div></div> : null}
    </div>
  );
}

function Sidebar({ activeView, collapsed, userId, onUserIdChange, onToggle, onViewChange }: { activeView: ViewKey; collapsed: boolean; userId: string; onUserIdChange: (value: string) => void; onToggle: () => void; onViewChange: (view: ViewKey) => void; }) {
  return <aside className={`fixed inset-y-0 left-0 z-40 hidden border-r border-white/10 bg-brand-navy text-white transition-[width] duration-200 lg:block ${collapsed ? "w-20" : "w-sidebar"}`}><div className="flex h-full flex-col"><div className="flex items-center justify-between gap-3 border-b border-white/10 p-4"><ProductMark collapsed={collapsed} /><IconButton label={collapsed ? "Expandir barra lateral" : "Contraer barra lateral"} onClick={onToggle}>{collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}</IconButton></div><nav className="grid gap-1 px-3 py-4">{navItems.map((item) => <NavButton key={item.key} item={item} active={activeView === item.key} collapsed={collapsed} onClick={() => onViewChange(item.key)} />)}</nav><UserPanel collapsed={collapsed} userId={userId} onUserIdChange={onUserIdChange} /></div></aside>;
}

function MobileSidebar({ activeView, userId, onUserIdChange, onClose, onViewChange }: { activeView: ViewKey; userId: string; onUserIdChange: (value: string) => void; onClose: () => void; onViewChange: (view: ViewKey) => void; }) {
  return <div className="flex h-full flex-col text-white"><div className="flex items-center justify-between border-b border-white/10 p-4"><ProductMark collapsed={false} /><IconButton label="Cerrar navegacion" onClick={onClose}><X className="h-4 w-4" /></IconButton></div><nav className="grid gap-1 px-3 py-4">{navItems.map((item) => <NavButton key={item.key} item={item} active={activeView === item.key} collapsed={false} onClick={() => onViewChange(item.key)} />)}</nav><UserPanel collapsed={false} userId={userId} onUserIdChange={onUserIdChange} /></div>;
}

function ProductMark({ collapsed }: { collapsed: boolean }) { return <div className="flex min-w-0 items-center gap-3"><div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-panel bg-brand-teal text-white"><ClipboardList className="h-5 w-5" aria-hidden /></div>{!collapsed ? <div className="min-w-0"><p className="truncate text-sm font-semibold">SmartQuote AI</p><p className="text-xs text-slate-300">Compras automatizadas</p></div> : null}</div>; }
function NavButton({ item, active, collapsed, onClick }: { item: { key: ViewKey; label: string; icon: ReactNode }; active: boolean; collapsed: boolean; onClick: () => void; }) { const button = <button className={`flex h-11 items-center gap-3 rounded-panel px-3 text-left text-sm font-medium transition ${active ? "bg-white text-brand-navy shadow-sm" : "text-slate-300 hover:bg-white/10 hover:text-white"} ${collapsed ? "justify-center" : ""}`} type="button" onClick={onClick} aria-current={active ? "page" : undefined}><span className="shrink-0">{item.icon}</span>{!collapsed ? <span className="truncate">{item.label}</span> : null}</button>; return collapsed ? <Tooltip text={item.label}>{button}</Tooltip> : button; }
function UserPanel({ collapsed, userId, onUserIdChange }: { collapsed: boolean; userId: string; onUserIdChange: (value: string) => void; }) { return <div className="mt-auto border-t border-white/10 p-4"><div className={`flex items-center gap-2 text-xs font-medium text-slate-300 ${collapsed ? "justify-center" : ""}`}><Settings2 className="h-4 w-4 shrink-0" aria-hidden />{!collapsed ? <span>Usuario activo</span> : null}</div>{!collapsed ? <Tooltip text={userId}><input className="mt-2 h-10 w-full rounded-control border border-white/10 bg-white/10 px-2 font-mono text-[11px] text-white outline-none transition placeholder:text-slate-400 focus:border-brand-teal" value={userId} onChange={(event) => onUserIdChange(event.target.value)} aria-label="Usuario activo" /></Tooltip> : null}</div>; }
