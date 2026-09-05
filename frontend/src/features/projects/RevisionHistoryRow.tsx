/**
 * One real historical `Sürüm` row: "Önizle" (an ephemeral, revision-scoped
 * preview — never the current revision, never a new revision, never a
 * mutation of `ProjectRegistry`/`CandidateLedger`) and "Bu sürüme geri dön"
 * (a real restore proposal over the SAME change/restore job slot Product
 * Detail's own "Değişikliği Başlat" already uses).
 *
 * Extracted from `ProjectDetail.tsx` because each row needs its OWN
 * `usePreview` instance — React's own rule against calling hooks in a loop
 * means one row = one component, not one hook call per array element
 * inlined in the parent.
 */

import type { ArkaliApiClient } from '@/api/client';
import type { RevisionResponse } from '@/api/contracts';
import { Button } from '@/components/ui';
import { PreviewStatusPanel } from '@/features/factory/PreviewControls';
import { usePreview } from '@/features/factory/usePreview';
import type { ProductChangeActions, ProductChangeState } from './useProductChange';

export function RevisionHistoryRow({
  client, projectId, revision, showTechnical, change,
}: {
  client: ArkaliApiClient;
  projectId: string;
  revision: RevisionResponse;
  showTechnical: boolean;
  /** The project's own single change-or-restore proposal slot — a real
   * restore may only be started while nothing else is active, matching
   * the backend's own one-slot-per-project reality exactly. */
  change: ProductChangeState & ProductChangeActions;
}) {
  const preview = usePreview(client, revision.revision_id, 'revision', projectId);
  const changeIsActive = change.job !== null
    && !['SUCCEEDED', 'FAILED', 'CANCELLED', 'DEAD_LETTER'].includes(change.job.lifecycle_state);

  return (
    <div className="flex flex-col gap-2 rounded-md border border-slate-200 px-3 py-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className={showTechnical ? 'font-mono text-sm text-slate-900' : 'text-sm text-slate-700'}>
          {showTechnical ? revision.revision_id : `Sürüm ${revision.sequence}`}
        </span>
        <div className="flex items-center gap-2">
          {preview.job === null || preview.job.lifecycle_state === 'CANCELLED' ? (
            <Button busy={preview.starting} onClick={() => void preview.open()}>
              Önizle
            </Button>
          ) : null}
          <Button
            busy={change.starting}
            disabled={changeIsActive}
            title={changeIsActive ? 'Devam eden bir değişiklik veya geri dönüş isteği var.' : undefined}
            onClick={() => void change.startRestore(revision.revision_id)}
          >
            Bu sürüme geri dön
          </Button>
        </div>
      </div>
      <PreviewStatusPanel
        preview={preview}
        showTechnical={showTechnical}
        technicalDetail={preview.job === null ? undefined : (
          `job_id: ${preview.job.job_id} · lifecycle_state: ${preview.job.lifecycle_state}`
        )}
      />
    </div>
  );
}
