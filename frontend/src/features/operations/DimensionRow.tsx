import type { DimensionReading } from '@/api/contracts';

/**
 * One telemetry dimension, presented exactly as the backend reported it.
 *
 * `value` is rendered only when `state === 'PASS'` — the same rule
 * `DimensionReading.real`/`.not_configured` enforce on the backend. A
 * `NOT_CONFIGURED`/`NOT_APPLICABLE` reading shows its own honest `detail`
 * text instead, never a placeholder number and never a hidden row: an
 * absent capability is real information, not noise to suppress.
 */

const BYTE_DIMENSIONS = new Set([
  'ram_total_bytes',
  'disk_free_bytes',
  'vram_total_bytes',
  'database_size_bytes',
]);

function formatBytes(bytes: number): string {
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(1)} ${units[unitIndex]}`;
}

function formatValue(dimension: string, value: number): string {
  if (BYTE_DIMENSIONS.has(dimension)) {
    return formatBytes(value);
  }
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

const STATE_TONE: Record<string, string> = {
  PASS: 'bg-emerald-50 text-emerald-800 ring-emerald-600/20',
  NOT_CONFIGURED: 'bg-slate-100 text-slate-600 ring-slate-500/20',
  NOT_APPLICABLE: 'bg-slate-100 text-slate-600 ring-slate-500/20',
  FAIL: 'bg-rose-50 text-rose-800 ring-rose-600/20',
};

export function DimensionRow({ reading }: { reading: DimensionReading }) {
  const tone = STATE_TONE[reading.state] ?? 'bg-slate-100 text-slate-600 ring-slate-500/20';
  return (
    <div className="flex items-start justify-between gap-3 py-2.5">
      <div className="min-w-0">
        <p className="text-sm font-medium text-slate-900">{reading.dimension}</p>
        <p className="mt-0.5 break-words text-xs text-slate-500">{reading.detail}</p>
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1">
        {reading.state === 'PASS' && reading.value !== null ? (
          <span className="font-mono text-sm font-semibold text-slate-900">
            {formatValue(reading.dimension, reading.value)}
          </span>
        ) : null}
        <span
          className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset ${tone}`}
        >
          {reading.state}
        </span>
      </div>
    </div>
  );
}
