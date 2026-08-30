/**
 * View state for the AI Software Factory history page.
 *
 * A VIEW OF THE LATEST READ, NOT A LIVE STREAM. `GET /api/factory/history`
 * re-derives its answer from the pipeline's own ledgers on every call
 * (`FactoryHistorySnapshot`'s own contract); this hook holds exactly what
 * the most recent read returned and nothing more. Production history
 * changes only when a real `golden-work-*` run finishes — there is no
 * polling here, only an explicit reload, the honest match for data that
 * does not change on its own between two page views.
 *
 * `stale` is true when the data on screen is not from the most recent
 * attempt: a previous read succeeded, a later one failed, and this hook
 * keeps showing the last real snapshot rather than blanking it.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { ApiRefusal, ApiUnavailable, type ArkaliApiClient } from '@/api/client';
import type { FactoryHistorySnapshot } from '@/api/contracts';

export interface Failure {
  readonly code: string;
  readonly message: string;
}

export interface FactoryHistoryState {
  readonly snapshot: FactoryHistorySnapshot | null;
  readonly loading: boolean;
  readonly refreshing: boolean;
  readonly failure: Failure | null;
  readonly stale: boolean;
}

export interface FactoryHistoryActions {
  reload: () => void;
}

function asFailure(error: unknown): Failure {
  if (error instanceof ApiRefusal) {
    return { code: error.code, message: error.message };
  }
  if (error instanceof ApiUnavailable) {
    return { code: 'UNREACHABLE', message: error.message };
  }
  return { code: 'UNEXPECTED', message: 'An unexpected error occurred.' };
}

export function useFactoryHistory(
  client: ArkaliApiClient,
): FactoryHistoryState & FactoryHistoryActions {
  const [snapshot, setSnapshot] = useState<FactoryHistorySnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);

  const controllerRef = useRef<AbortController | null>(null);
  const inFlightRef = useRef(false);

  const fetchOnce = useCallback(() => {
    if (inFlightRef.current) {
      return;
    }
    inFlightRef.current = true;
    const controller = new AbortController();
    controllerRef.current = controller;
    setRefreshing(true);
    client
      .factoryHistory(controller.signal)
      .then((result) => {
        if (controller.signal.aborted) {
          return;
        }
        setSnapshot(result);
        setFailure(null);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        setFailure(asFailure(error));
      })
      .finally(() => {
        if (controller.signal.aborted) {
          return;
        }
        inFlightRef.current = false;
        controllerRef.current = null;
        setLoading(false);
        setRefreshing(false);
      });
  }, [client]);

  const reload = useCallback(() => {
    controllerRef.current?.abort();
    inFlightRef.current = false;
    fetchOnce();
  }, [fetchOnce]);

  useEffect(() => {
    fetchOnce();
    return () => {
      controllerRef.current?.abort();
      inFlightRef.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client]);

  return {
    snapshot,
    loading,
    refreshing,
    failure,
    stale: snapshot !== null && failure !== null,
    reload,
  };
}
