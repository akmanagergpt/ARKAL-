/**
 * View state for the Tanılama page (Command Center Wave 2C, Surface C).
 *
 * A VIEW OF THE LATEST SNAPSHOT, NOT A LIVE STREAM - the identical contract
 * `useProvidersSnapshot`/`useCodeIntelligenceSnapshot` already established:
 * no polling for V1, fetched on mount and on an explicit "Yenile". The
 * backend re-derives every figure from real owners on each call, so a
 * stale client-side cache would only ever mislead.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { ApiRefusal, ApiUnavailable, type ArkaliApiClient } from '@/api/client';
import type { _DiagnosticsSnapshotResponse } from '@/api/contracts';

export interface Failure {
  readonly code: string;
  readonly message: string;
}

export interface DiagnosticsState {
  readonly snapshot: _DiagnosticsSnapshotResponse | null;
  readonly loading: boolean;
  readonly refreshing: boolean;
  readonly failure: Failure | null;
}

export interface DiagnosticsActions {
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

export function useDiagnosticsSnapshot(
  client: ArkaliApiClient,
): DiagnosticsState & DiagnosticsActions {
  const [snapshot, setSnapshot] = useState<_DiagnosticsSnapshotResponse | null>(null);
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
      .diagnosticsSnapshot(controller.signal)
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

  return { snapshot, loading, refreshing, failure, reload };
}
