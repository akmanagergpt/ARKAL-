/**
 * View state for the Operations page (`ARK-REQ-0396`, D-028).
 *
 * A VIEW OF THE LATEST SNAPSHOT, NOT A LIVE STREAM. Every render shows
 * exactly what the backend returned on the most recent call — there is no
 * client-side derivation, no smoothing, no cached fallback value substituted
 * when a dimension reports `NOT_CONFIGURED`. Reload replaces the whole
 * snapshot, mirroring `OperationsSnapshot`'s own "nothing is cached, a
 * second call re-derives it from scratch" contract.
 *
 * POLLING IS BOUNDED AND VISIBILITY-AWARE. One request is ever in flight at a
 * time — a tick that lands while the previous request is still outstanding is
 * skipped rather than queued or fired in parallel. Polling pauses while the
 * tab is hidden (`document.visibilityState`) and a single catch-up read fires
 * when it becomes visible again, so the surface never holds an open
 * connection or spends requests a nobody is looking at.
 *
 * `stale` is true when the data on screen is not from the most recent
 * attempt: a previous fetch succeeded, a later one failed, and this hook
 * keeps showing the last real snapshot rather than blanking it — the failure
 * is surfaced alongside it instead of replacing it.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { ApiRefusal, ApiUnavailable, type ArkaliApiClient } from '@/api/client';
import type { OperationsSnapshot } from '@/api/contracts';

export const POLL_INTERVAL_MS = 15_000;

export interface Failure {
  readonly code: string;
  readonly message: string;
}

export interface OperationsState {
  readonly snapshot: OperationsSnapshot | null;
  readonly loading: boolean;
  readonly refreshing: boolean;
  readonly failure: Failure | null;
  readonly stale: boolean;
  readonly lastUpdatedAt: number | null;
}

export interface OperationsActions {
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

export function useOperationsSnapshot(
  client: ArkaliApiClient,
): OperationsState & OperationsActions {
  const [snapshot, setSnapshot] = useState<OperationsSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(null);

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
      .operationsSnapshot(controller.signal)
      .then((result) => {
        if (controller.signal.aborted) {
          return;
        }
        setSnapshot(result);
        setFailure(null);
        setLastUpdatedAt(Date.now());
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

    const interval = window.setInterval(() => {
      if (document.visibilityState === 'visible') {
        fetchOnce();
      }
    }, POLL_INTERVAL_MS);

    function onVisible() {
      if (document.visibilityState === 'visible') {
        fetchOnce();
      }
    }
    document.addEventListener('visibilitychange', onVisible);

    return () => {
      window.clearInterval(interval);
      document.removeEventListener('visibilitychange', onVisible);
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
    lastUpdatedAt,
    reload,
  };
}
