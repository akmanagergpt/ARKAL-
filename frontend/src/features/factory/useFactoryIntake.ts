/**
 * View state for the "Yeni Uygulama" real goal-intake form.
 *
 * ONE REAL CALL, ONE REAL ANSWER, THEN REAL POLLING WHEN THERE IS SOMETHING
 * REAL TO POLL. `result` holds exactly what `POST /api/factory/goals`
 * returned — `ProductionIntake`, unmodified in shape. When that result
 * carries a real `durable_job_id` (`state === 'queued'`), this hook polls
 * the real `GET /api/jobs/{job_id}` and `GET /api/jobs/{job_id}/checkpoints`
 * — the real C-19 job store, never a second progress-state store — until
 * the job reaches a state the UI treats as done. Nothing here simulates a
 * stage that did not really happen.
 *
 * KNOWN LIMIT: A BROWSER REFRESH LOSES THE POLL, NOT THE JOB. `job`/
 * `checkpoints` live only in this hook's own React state, which a refresh
 * clears — resuming it would need either a new "list my active jobs" route
 * (a real, honest extension, just not built this turn) or browser storage
 * standing in for backend truth, which `test_frontend_boundaries.py`
 * forbids outright. The real job and every real checkpoint stay exactly as
 * they were in the database regardless; only this tab's own view of them
 * is lost.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { ApiRefusal, ApiUnavailable, type ArkaliApiClient } from '@/api/client';
import type {
  _FactoryIntakeResponse,
  _JobCheckpointResponse,
  JobReferenceResponse,
} from '@/api/contracts';

export interface Failure {
  readonly code: string;
  readonly message: string;
}

//: Once a real job reaches one of these, this hook stops polling. `FAILED`
//: is included even though the canonical Job machine does not mark it
//: `terminal` (a failed job can still reach `RECOVERABLE`/`DEAD_LETTER`) —
//: that is a real backend recovery concern, not a reason to keep this
//: screen's own spinner running after the outcome is already known.
const DONE_STATES: ReadonlySet<string> = new Set([
  'SUCCEEDED', 'FAILED', 'CANCELLED', 'DEAD_LETTER',
]);
const POLL_INTERVAL_MS = 4000;

export interface FactoryIntakeState {
  readonly submitting: boolean;
  readonly result: _FactoryIntakeResponse | null;
  readonly failure: Failure | null;
  readonly job: JobReferenceResponse | null;
  readonly checkpoints: readonly _JobCheckpointResponse[];
}

export interface FactoryIntakeActions {
  submit: (goalText: string) => Promise<void>;
  reset: () => void;
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

/** A real, unique-per-submission request id. Not a second identity
 * authority — the backend derives `goal_id`/`blueprint_id` on its own from
 * `goal_text`; this only lets the same click be told apart from the next. */
function deriveRequestId(): string {
  return `goal-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

export function useFactoryIntake(client: ArkaliApiClient): FactoryIntakeState & FactoryIntakeActions {
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<_FactoryIntakeResponse | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [job, setJob] = useState<JobReferenceResponse | null>(null);
  const [checkpoints, setCheckpoints] = useState<readonly _JobCheckpointResponse[]>([]);

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
        }
      } catch {
        // A transient read failure does not end the poll — the next real
        // tick tries again. The job itself is durable; this tab's own
        // view of it is what may be briefly stale.
      }
    },
    [client, stopPolling],
  );

  const submit = useCallback(
    async (goalText: string): Promise<void> => {
      stopPolling();
      setSubmitting(true);
      setFailure(null);
      setJob(null);
      setCheckpoints([]);
      try {
        const response = await client.submitFactoryGoal({
          request_id: deriveRequestId(),
          goal_text: goalText,
          capability_id: null,
        });
        setResult(response);
        if (response.durable_job_id !== null) {
          const jobId = response.durable_job_id;
          void pollOnce(jobId);
          pollRef.current = setInterval(() => {
            void pollOnce(jobId);
          }, POLL_INTERVAL_MS);
        }
      } catch (error: unknown) {
        setFailure(asFailure(error));
        setResult(null);
      } finally {
        setSubmitting(false);
      }
    },
    [client, pollOnce, stopPolling],
  );

  const reset = useCallback(() => {
    stopPolling();
    setResult(null);
    setFailure(null);
    setJob(null);
    setCheckpoints([]);
  }, [stopPolling]);

  return { submitting, result, failure, job, checkpoints, submit, reset };
}
