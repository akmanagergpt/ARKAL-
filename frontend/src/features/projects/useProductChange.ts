/**
 * View state for "Değişikliği Başlat" / "Kabul Et" / "Vazgeç" (D-030 V1) —
 * a real `managed_product.change` durable job, never a second progress-
 * state store. Mirrors `usePreview`'s own shape exactly: refresh recovery
 * is a plain read on mount, `start` is idempotent by the backend's own
 * persisted unique constraint, and "Vazgeç" reuses the identical
 * `cancelJob` call "Durdur" already uses — the worker that owns the real
 * review preview is the only thing that ever observes it and acts.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { ApiRefusal, ApiUnavailable, type ArkaliApiClient } from '@/api/client';
import type { _ChangePromotionResponse, _JobCheckpointResponse, JobReferenceResponse } from '@/api/contracts';

export interface ChangeFailure {
  readonly code: string;
  readonly message: string;
}

const DONE_STATES: ReadonlySet<string> = new Set(['SUCCEEDED', 'FAILED', 'CANCELLED', 'DEAD_LETTER']);
const POLL_INTERVAL_MS = 3000;

export interface ReadyChange {
  readonly frontendUrl: string;
  readonly backendUrl: string;
}

export interface ProductChangeState {
  readonly starting: boolean;
  readonly promoting: boolean;
  readonly rejecting: boolean;
  readonly job: JobReferenceResponse | null;
  readonly checkpoints: readonly _JobCheckpointResponse[];
  /** Non-null once the worker's own real `ready_for_review` checkpoint has
   * been observed — the real, live preview of the PROPOSED change is up at
   * these URLs, awaiting a human decision. */
  readonly ready: ReadyChange | null;
  readonly promoted: _ChangePromotionResponse | null;
  readonly failure: ChangeFailure | null;
}

export interface ProductChangeActions {
  start: (requestText: string) => Promise<void>;
  promote: () => Promise<void>;
  reject: () => Promise<void>;
}

function asFailure(error: unknown): ChangeFailure {
  if (error instanceof ApiRefusal) {
    return { code: error.code, message: error.message };
  }
  if (error instanceof ApiUnavailable) {
    return { code: 'UNREACHABLE', message: error.message };
  }
  return { code: 'UNEXPECTED', message: 'Beklenmeyen bir hata oluştu.' };
}

function readyFrom(checkpoints: readonly _JobCheckpointResponse[]): ReadyChange | null {
  for (let i = checkpoints.length - 1; i >= 0; i -= 1) {
    const payload = checkpoints[i]?.payload;
    if (payload?.phase === 'ready_for_review') {
      const frontendUrl = payload.frontend_url;
      const backendUrl = payload.backend_url;
      if (typeof frontendUrl === 'string' && typeof backendUrl === 'string') {
        return { frontendUrl, backendUrl };
      }
    }
  }
  return null;
}

export function useProductChange(
  client: ArkaliApiClient, projectId: string, onPromoted?: () => void,
): ProductChangeState & ProductChangeActions {
  const [starting, setStarting] = useState(false);
  const [promoting, setPromoting] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [job, setJob] = useState<JobReferenceResponse | null>(null);
  const [checkpoints, setCheckpoints] = useState<readonly _JobCheckpointResponse[]>([]);
  const [promoted, setPromoted] = useState<_ChangePromotionResponse | null>(null);
  const [failure, setFailure] = useState<ChangeFailure | null>(null);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);
  useEffect(() => stopPolling, [stopPolling]);

  const ready = useMemo(() => readyFrom(checkpoints), [checkpoints]);

  const pollOnce = useCallback(
    async (jobId: string): Promise<void> => {
      try {
        const [jobRef, jobCheckpoints] = await Promise.all([
          client.getJob(jobId),
          client.listJobCheckpoints(jobId),
        ]);
        setJob(jobRef);
        setCheckpoints(jobCheckpoints);
        if (DONE_STATES.has(jobRef.lifecycle_state)) {
          stopPolling();
        }
      } catch {
        // A transient read failure does not end the poll -- the real job
        // is durable; only this tab's own view of it may be briefly stale.
      }
    },
    [client, stopPolling],
  );

  useEffect(() => {
    if (projectId === '') {
      return undefined;
    }
    let cancelled = false;
    void (async () => {
      let reference: JobReferenceResponse | null;
      try {
        reference = await client.findProjectChange(projectId);
      } catch {
        return;
      }
      if (cancelled || reference === null) {
        return;
      }
      setJob(reference);
      try {
        setCheckpoints(await client.listJobCheckpoints(reference.job_id));
      } catch {
        // real job, momentarily unreadable checkpoints -- the next poll retries
      }
      if (!cancelled && !DONE_STATES.has(reference.lifecycle_state)) {
        pollRef.current = setInterval(() => {
          void pollOnce(reference.job_id);
        }, POLL_INTERVAL_MS);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once per selected project
  }, [projectId]);

  const start = useCallback(
    async (requestText: string): Promise<void> => {
      stopPolling();
      setStarting(true);
      setFailure(null);
      setPromoted(null);
      try {
        const reference = await client.startProjectChange(projectId, requestText);
        setJob(reference);
        setCheckpoints(await client.listJobCheckpoints(reference.job_id).catch(() => []));
        if (!DONE_STATES.has(reference.lifecycle_state)) {
          pollRef.current = setInterval(() => {
            void pollOnce(reference.job_id);
          }, POLL_INTERVAL_MS);
        }
      } catch (error: unknown) {
        setFailure(asFailure(error));
      } finally {
        setStarting(false);
      }
    },
    [client, projectId, pollOnce, stopPolling],
  );

  const promote = useCallback(async (): Promise<void> => {
    if (job === null) {
      return;
    }
    setPromoting(true);
    setFailure(null);
    try {
      const result = await client.promoteProjectChange(projectId, job.job_id);
      setPromoted(result);
      // The worker's own next poll observes the real `promoted` checkpoint
      // it just left and transitions the job SUCCEEDED a few seconds
      // later; this poll keeps running so the UI reflects that real fact
      // once it happens, rather than this click pretending it already did.
      onPromoted?.();
    } catch (error: unknown) {
      setFailure(asFailure(error));
    } finally {
      setPromoting(false);
    }
  }, [client, projectId, job, onPromoted]);

  const reject = useCallback(async (): Promise<void> => {
    if (job === null) {
      return;
    }
    setRejecting(true);
    setFailure(null);
    try {
      await client.cancelJob(job.job_id);
    } catch (error: unknown) {
      setFailure(asFailure(error));
    } finally {
      setRejecting(false);
    }
  }, [client, job]);

  return {
    starting, promoting, rejecting, job, checkpoints, ready, promoted, failure,
    start, promote, reject,
  };
}
