import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

interface DialogProps {
  open: boolean;
  title: string;
  description: string;
  children: ReactNode;
  onClose: () => void;
  destructive?: boolean;
}

export function Dialog({ open, title, description, children, onClose, destructive = false }: DialogProps) {
  const panel = useRef<HTMLDivElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    previousFocus.current = document.activeElement as HTMLElement;
    const focusable = panel.current?.querySelector<HTMLElement>("button, input, select, textarea, a[href]");
    focusable?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !destructive) onClose();
      if (event.key !== "Tab" || !panel.current) return;
      const items = Array.from(panel.current.querySelectorAll<HTMLElement>("button, input, select, textarea, a[href]"));
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = "";
      document.removeEventListener("keydown", onKeyDown);
      previousFocus.current?.focus();
    };
  }, [open, onClose, destructive]);

  if (!open) return null;
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onMouseDown={(event) => { if (event.target === event.currentTarget && !destructive) onClose(); }}>
      <div ref={panel} role="dialog" aria-modal="true" aria-labelledby="kibolens-dialog-title" aria-describedby="kibolens-dialog-description" className="w-full max-w-md rounded-xl border border-zinc-700 bg-zinc-900 p-6 shadow-2xl shadow-black/40">
        <h2 id="kibolens-dialog-title" className="text-lg font-semibold text-zinc-100">{title}</h2>
        <p id="kibolens-dialog-description" className="mt-2 text-sm leading-6 text-zinc-400">{description}</p>
        <div className="mt-6 flex justify-end gap-3">{children}</div>
      </div>
    </div>,
    document.body,
  );
}

export function ConfirmDialog({ open, title, description, onCancel, onConfirm, confirmLabel = "Confirm", destructive = false, busy = false }: {
  open: boolean; title: string; description: string; onCancel: () => void; onConfirm: () => void; confirmLabel?: string; destructive?: boolean; busy?: boolean;
}) {
  return <Dialog open={open} title={title} description={description} onClose={onCancel} destructive={destructive}>
    <button type="button" onClick={onCancel} disabled={busy} className="rounded-md border border-zinc-700 px-4 py-2 text-sm text-zinc-300 transition hover:border-zinc-500 hover:text-white disabled:opacity-50">Cancel</button>
    <button type="button" onClick={onConfirm} disabled={busy} className={`rounded-md px-4 py-2 text-sm font-medium transition disabled:opacity-50 ${destructive ? "bg-red-500 text-white hover:bg-red-400" : "bg-cyan-400 text-zinc-950 hover:bg-cyan-300"}`}>{busy ? "Working…" : confirmLabel}</button>
  </Dialog>;
}
