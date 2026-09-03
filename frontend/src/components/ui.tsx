/**
 * The restrained presentation baseline for the first Command Center slice.
 *
 * Deliberately small. The ARKALI design system is not this package's business;
 * what is, is that the slice presents state honestly — a control that is busy
 * says so, a refusal is shown as a refusal, and nothing is styled to look
 * enabled when it is not.
 */

import type { ReactNode } from 'react';

export function Button({
  children,
  type = 'button',
  onClick,
  disabled = false,
  busy = false,
  variant = 'secondary',
}: {
  children: ReactNode;
  type?: 'button' | 'submit';
  onClick?: () => void;
  disabled?: boolean;
  busy?: boolean;
  variant?: 'primary' | 'secondary';
}) {
  const palette =
    variant === 'primary'
      ? 'bg-slate-900 text-white hover:bg-slate-700 disabled:bg-slate-400'
      : 'bg-white text-slate-900 ring-1 ring-inset ring-slate-300 hover:bg-slate-100 disabled:text-slate-400';
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled || busy}
      aria-busy={busy}
      className={`inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed ${palette}`}
    >
      {busy ? <Spinner /> : null}
      {children}
    </button>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-slate-500">
      <span
        aria-hidden="true"
        className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-r-transparent"
      />
      {label === undefined ? null : <span className="text-sm">{label}</span>}
    </span>
  );
}

/** A labelled text input. The label is a real `<label>`, always. */
export function Field({
  id,
  label,
  value,
  onChange,
  hint,
  disabled = false,
  required = false,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (next: string) => void;
  hint?: string;
  disabled?: boolean;
  required?: boolean;
}) {
  const hintId = `${id}-hint`;
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium text-slate-800">
        {label}
        {required ? <span className="text-slate-500"> (zorunlu)</span> : null}
      </label>
      <input
        id={id}
        value={value}
        disabled={disabled}
        required={required}
        aria-describedby={hint === undefined ? undefined : hintId}
        onChange={(event) => onChange(event.target.value)}
        className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 disabled:bg-slate-100 disabled:text-slate-500"
      />
      {hint === undefined ? null : (
        <p id={hintId} className="text-xs text-slate-500">
          {hint}
        </p>
      )}
    </div>
  );
}

export function Callout({
  tone,
  title,
  children,
}: {
  tone: 'error' | 'success' | 'muted';
  title: string;
  children?: ReactNode;
}) {
  const palette = {
    error: 'border-rose-300 bg-rose-50 text-rose-900',
    success: 'border-emerald-300 bg-emerald-50 text-emerald-900',
    muted: 'border-slate-300 bg-slate-100 text-slate-700',
  }[tone];
  return (
    <div
      role={tone === 'error' ? 'alert' : 'status'}
      className={`rounded-md border px-3 py-2 text-sm ${palette}`}
    >
      <p className="font-semibold">{title}</p>
      {children === undefined ? null : <div className="mt-1">{children}</div>}
    </div>
  );
}

export function Panel({ title, actions, children }: {
  title: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  // `min-w-0`: a CSS grid/flex item's default min-width is `auto`, which
  // floors it at its content's min-content width. An unbreakable token inside
  // (a Windows path, a dotted identifier) can exceed the viewport before this
  // overrides that floor, so without it a narrow-viewport panel forces the
  // whole page to scroll horizontally instead of wrapping its own text.
  return (
    <section className="min-w-0 rounded-lg border border-slate-200 bg-white shadow-sm">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-4 py-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-600">
          {title}
        </h2>
        {actions}
      </header>
      <div className="p-4">{children}</div>
    </section>
  );
}

/**
 * The lifecycle state as the backend reported it.
 *
 * Rendered as an opaque value on purpose: there is no per-state styling,
 * because a style table keyed by state name would be this file holding an
 * opinion about the machine's states. `showTechnical` (default true, so
 * every existing caller that predates this prop is unaffected) only ever
 * swaps the LABEL for a plain Turkish word — the real `state` string this
 * component receives, and would render literally, is never altered,
 * invented or hidden from anyone who asks for it (Uzman mode still shows
 * it verbatim). A state absent from the map (any real state the machine
 * could ever add) falls back to the raw value rather than silently
 * showing nothing — this file still holds no opinion about which states
 * exist, only about how five already-canonical ones read in Turkish.
 */
const PROJECT_STATE_LABELS_TR: Readonly<Record<string, string>> = {
  DRAFT: 'Taslak',
  SPECIFIED: 'Belirlendi',
  ACTIVE: 'Aktif',
  SUSPENDED: 'Askıya Alındı',
  ARCHIVED: 'Arşivlendi',
};

/** Exported so any other real caller needing this same translation (e.g. a
 * lifecycle-transition picker) reuses one table rather than growing a
 * second copy of it. */
export function projectStateLabel(state: string): string {
  return PROJECT_STATE_LABELS_TR[state] ?? state;
}

export function StateBadge({ state, showTechnical = true }: { state: string; showTechnical?: boolean }) {
  const label = showTechnical ? state : projectStateLabel(state);
  return (
    <span
      className="inline-flex rounded-full bg-slate-900 px-2.5 py-0.5 font-mono text-xs font-medium text-white"
      title={showTechnical ? undefined : state}
    >
      {label}
    </span>
  );
}
