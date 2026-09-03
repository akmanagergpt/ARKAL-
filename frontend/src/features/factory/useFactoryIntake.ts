/**
 * View state for the "Yeni Uygulama" real goal-intake form.
 *
 * ONE REAL CALL, ONE REAL ANSWER. This hook holds exactly what the most
 * recent `POST /api/factory/goals` returned — `ProductionIntake`, unmodified
 * in shape — and nothing invented between submission and answer. There is no
 * polling here and no simulated progress: `state` on the response is
 * terminal the instant it comes back (`governed_stop`, `escalated`, or a
 * `queued` that nothing in the running Command Center currently consumes —
 * see `NewApplicationIntake.tsx`'s own doc comment for why).
 */

import { useCallback, useState } from 'react';

import { ApiRefusal, ApiUnavailable, type ArkaliApiClient } from '@/api/client';
import type { _FactoryIntakeResponse } from '@/api/contracts';

export interface Failure {
  readonly code: string;
  readonly message: string;
}

export interface FactoryIntakeState {
  readonly submitting: boolean;
  readonly result: _FactoryIntakeResponse | null;
  readonly failure: Failure | null;
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

  const submit = useCallback(
    async (goalText: string): Promise<void> => {
      setSubmitting(true);
      setFailure(null);
      try {
        const response = await client.submitFactoryGoal({
          request_id: deriveRequestId(),
          goal_text: goalText,
          capability_id: null,
        });
        setResult(response);
      } catch (error: unknown) {
        setFailure(asFailure(error));
        setResult(null);
      } finally {
        setSubmitting(false);
      }
    },
    [client],
  );

  const reset = useCallback(() => {
    setResult(null);
    setFailure(null);
  }, []);

  return { submitting, result, failure, submit, reset };
}
