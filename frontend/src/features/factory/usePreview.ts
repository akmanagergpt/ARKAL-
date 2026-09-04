/**
 * View state for "Uygulamayı Aç" / "Durdur" — a real `candidate.preview`
 * durable job, never a second progress-state store.
 *
 * REFRESH RECOVERY IS A READ, NEVER A CLIENT-STORAGE GUESS. On mount, this
 * hook calls the real, read-only `GET /candidates/{id}/preview` — it
 * either rediscovers the real job C-19 already holds for this candidate
 * (opening, ready, or already stopped) or finds honestly nothing, and
 * either way nothing is created just by loading the page. "Uygulamayı Aç"
 * itself calls `POST /candidates/{id}/preview`, a real user action, which
 * is idempotent by the backend's own persisted unique constraint — the
 * same identity request after a refresh returns the real, already-running
 * job rather than a duplicate.
 *
 * KNOWN LIMIT (same shape as `useFactoryIntake`'s own documented one): once
 * this identity reaches a terminal state (CANCELLED, most commonly a real
 * "Durdur"), the same candidate cannot start a *new* preview under this
 * identity again this session — re-opening needs a fresh identity scheme,
 * not built this turn.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { ApiRefusal, ApiUnavailable, type ArkaliApiClient } from '@/api/client';
import type { _JobCheckpointResponse, JobReferenceResponse } from '@/api/contracts';

export interface Failure {
  readonly code: string;
  readonly message: string;
}

const DONE_STATES: ReadonlySet<string> = new Set(['SUCCEEDED', 'FAILED', 'CANCELLED', 'DEAD_LETTER']);
const POLL_INTERVAL_MS = 3000;

export interface PreviewState {
  readonly starting: boolean;
  readonly cancelling: boolean;
  /**
   * Local interaction state only — NOT a canonical backend state, and it
   * never overrides `job.lifecycle_state`. It means exactly one thing: a
   * real cancel request was sent and this tab has not yet observed the
   * worker's own real CANCELLED transition. It exists only so the UI can
   * say "Durdurma isteği gönderildi…" honestly during that real gap,
   * instead of either freezing on the last-seen state or pretending the
   * job is already stopped before it actually is.
   */
  readonly stopRequested: boolean;
  readonly job: JobReferenceResponse | null;
  readonly checkpoints: readonly _JobCheckpointResponse[];
  readonly failure: Failure | null;
}

export interface PreviewActions {
  open: () => Promise<void>;
  stop: () => Promise<void>;
}

function asFailure(error: unknown): Failure {
  if (error instanceof ApiRefusal) {
    return { code: error.code, message: error.message };
  }
  if (error instanceof ApiUnavailable) {
    return { code: 'UNREACHABLE', message: error.message };
  }
  return { code: 'UNEXPECTED', message: 'Beklenmeyen bir hata oluştu.' };
}

export function usePreview(
  client: ArkaliApiClient, candidateId: string,
): PreviewState & PreviewActions {
  const [starting, setStarting] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [stopRequested, setStopRequested] = useState(false);
  const [job, setJob] = useState<JobReferenceResponse | null>(null);
  const [checkpoints, setCheckpoints] = useState<readonly _JobCheckpointResponse[]>([]);
  const [failure, setFailure] = useState<Failure | null>(null);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

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
        } else {
          // A checkpoint recorded after the cancel request means the
          // worker has now genuinely acted on it -- the real gap
          // `stopRequested` exists for is over even though the terminal
          // transition itself may land a tick later.
          const cancelSeen = jobCheckpoints.some((c) => c.payload.phase === 'cancel_requested');
          if (cancelSeen) {
            setStopRequested(true);
          }
        }
      } catch {
        // A transient read failure does not end the poll -- the real job
        // is durable; only this tab's own view of it may be briefly stale.
      }
    },
    [client, stopPolling],
  );

  // Refresh recovery: a plain read on mount, never a client-storage guess
  // and never something that creates a job just by loading the page.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      let reference: JobReferenceResponse | null;
      try {
        reference = await client.findPreview(candidateId);
      } catch {
        return; // nothing rediscoverable is not an error the user needs to see
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
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once per mounted candidate row
  }, [candidateId]);

  const open = useCallback(async (): Promise<void> => {
    stopPolling();
    setStarting(true);
    setFailure(null);
    setStopRequested(false);
    try {
      const reference = await client.startPreview(candidateId);
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
  }, [candidateId, client, pollOnce, stopPolling]);

  const stop = useCallback(async (): Promise<void> => {
    if (job === null) {
      return;
    }
    setCancelling(true);
    try {
      // Real "Durdur" never transitions the job itself (only the worker
      // that owns the actual processes does that -- see jobs.py's own
      // `cancel_job` docstring) -- it only records a real request. Polling
      // is deliberately left running: it is what will observe the worker's
      // own real CANCELLED transition once it happens, a few real seconds
      // later, not something this click can shortcut.
      await client.cancelJob(job.job_id);
      setStopRequested(true);
    } catch (error: unknown) {
      setFailure(asFailure(error));
    } finally {
      setCancelling(false);
    }
  }, [client, job]);

  return { starting, cancelling, stopRequested, job, checkpoints, failure, open, stop };
}
