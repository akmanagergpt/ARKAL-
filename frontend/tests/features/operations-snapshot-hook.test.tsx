/**
 * `useOperationsSnapshot` in isolation: polling cadence, visibility awareness
 * and request cancellation are behaviours a rendered page cannot exercise
 * deterministically (they depend on fake timers and inspecting the request
 * that is actually in flight), so they are tested directly against the hook.
 *
 * FAKE TIMERS, FLUSHED BY HAND. `waitFor`'s internal polling uses real
 * timers, which never fire once `vi.useFakeTimers()` is active - mixing the
 * two hangs a test until it times out. Every wait below instead advances the
 * fake clock (`vi.advanceTimersByTimeAsync`), which also drains the
 * microtask queue a resolved fetch promise needs to reach `useState`.
 */

import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ArkaliApiClient } from '@/api/client';
import { OPERATIONS_SNAPSHOT } from '../fixtures';
import { POLL_INTERVAL_MS, useOperationsSnapshot } from '@/features/operations/useOperationsSnapshot';

const BASE = 'http://127.0.0.1:8000';

interface PendingRequest {
  readonly url: string;
  readonly signal: AbortSignal | undefined;
  resolve(body: unknown): void;
  fail(): void;
}

function controllableFetch() {
  const pending: PendingRequest[] = [];
  const fetchImpl = ((input: RequestInfo | URL, init?: RequestInit) => {
    return new Promise<Response>((resolve, reject) => {
      const signal = init?.signal ?? undefined;
      signal?.addEventListener('abort', () => {
        reject(new DOMException('Aborted', 'AbortError'));
      });
      pending.push({
        url: String(input),
        signal,
        resolve: (body: unknown) =>
          resolve(
            new Response(JSON.stringify(body), {
              status: 200,
              headers: { 'Content-Type': 'application/json' },
            }),
          ),
        fail: () => reject(new Error('simulated network failure')),
      });
    });
  }) as typeof fetch;
  return { fetchImpl, pending };
}

function setVisibility(state: DocumentVisibilityState) {
  Object.defineProperty(document, 'visibilityState', { value: state, configurable: true });
}

/** Drains the microtask queue under fake timers without moving the clock. */
async function flush() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
}

afterEach(() => {
  vi.useRealTimers();
  setVisibility('visible');
});

describe('useOperationsSnapshot', () => {
  it('fetches once on mount and again after one poll interval while visible', async () => {
    vi.useFakeTimers();
    const { fetchImpl, pending } = controllableFetch();
    const client = new ArkaliApiClient({ baseUrl: BASE, fetchImpl });

    const { result, unmount } = renderHook(() => useOperationsSnapshot(client));
    expect(pending).toHaveLength(1);

    pending[0]!.resolve(OPERATIONS_SNAPSHOT);
    await flush();
    expect(result.current.snapshot).not.toBeNull();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(pending).toHaveLength(2);

    unmount();
  });

  it('does not poll while the tab is hidden, and catches up when it becomes visible', async () => {
    vi.useFakeTimers();
    const { fetchImpl, pending } = controllableFetch();
    const client = new ArkaliApiClient({ baseUrl: BASE, fetchImpl });

    const { unmount } = renderHook(() => useOperationsSnapshot(client));
    pending[0]!.resolve(OPERATIONS_SNAPSHOT);
    await flush();
    expect(pending).toHaveLength(1);

    setVisibility('hidden');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 2);
    });
    expect(pending).toHaveLength(1);

    setVisibility('visible');
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'));
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(pending).toHaveLength(2);

    unmount();
  });

  it('does not fire an overlapping request while one is already in flight', async () => {
    vi.useFakeTimers();
    const { fetchImpl, pending } = controllableFetch();
    const client = new ArkaliApiClient({ baseUrl: BASE, fetchImpl });

    const { unmount } = renderHook(() => useOperationsSnapshot(client));
    expect(pending).toHaveLength(1);

    // The mount request is still unresolved when the next poll tick lands.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(pending).toHaveLength(1);

    unmount();
  });

  it('aborts the in-flight request when the component unmounts', async () => {
    const { fetchImpl, pending } = controllableFetch();
    const client = new ArkaliApiClient({ baseUrl: BASE, fetchImpl });

    const { unmount } = renderHook(() => useOperationsSnapshot(client));
    const inFlight = pending[0]!;
    expect(inFlight.signal?.aborted).toBe(false);

    unmount();

    expect(inFlight.signal?.aborted).toBe(true);
  });

  it('aborts the previous request when a manual reload supersedes it', async () => {
    const { fetchImpl, pending } = controllableFetch();
    const client = new ArkaliApiClient({ baseUrl: BASE, fetchImpl });

    const { result } = renderHook(() => useOperationsSnapshot(client));
    const first = pending[0]!;

    act(() => result.current.reload());

    expect(first.signal?.aborted).toBe(true);
    await waitFor(() => expect(pending).toHaveLength(2));
  });

  it('keeps the last real snapshot and marks it stale when a later request fails', async () => {
    const { fetchImpl, pending } = controllableFetch();
    const client = new ArkaliApiClient({ baseUrl: BASE, fetchImpl });

    const { result } = renderHook(() => useOperationsSnapshot(client));
    act(() => pending[0]!.resolve(OPERATIONS_SNAPSHOT));
    await waitFor(() => expect(result.current.snapshot).not.toBeNull());
    expect(result.current.stale).toBe(false);

    act(() => result.current.reload());
    await waitFor(() => expect(pending).toHaveLength(2));
    act(() => pending[1]!.fail());

    await waitFor(() => expect(result.current.stale).toBe(true));
    // The last real snapshot is kept on screen, not blanked by the failure.
    expect(result.current.snapshot).not.toBeNull();
    expect(result.current.failure?.code).toBe('UNREACHABLE');
  });
});
