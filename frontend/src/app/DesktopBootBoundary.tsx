import { useEffect, useState, type ReactNode } from 'react';

import type { ArkaliApiClient } from '@/api/client';

type BootState = 'checking' | 'ready' | 'failed';

export function DesktopBootBoundary({ client, children }: {
  readonly client: ArkaliApiClient;
  readonly children: ReactNode;
}) {
  const [state, setState] = useState<BootState>('checking');
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    setState('checking');
    client.health().then(
      (health) => { if (active) setState(health.status === 'ready' ? 'ready' : 'failed'); },
      () => { if (active) setState('failed'); },
    );
    return () => { active = false; };
  }, [client, attempt]);

  if (state === 'ready') return children;

  return (
    <main className="grid min-h-screen place-items-center bg-slate-950 px-6 text-slate-100">
      <section className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900 p-8 shadow-2xl">
        <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-xl bg-emerald-400 text-xl font-black text-slate-950">A</div>
        {state === 'checking' ? (
          <>
            <h1 className="text-xl font-semibold">ARKALI hazırlanıyor</h1>
            <p className="mt-2 text-sm text-slate-400">Yerel Command Center ve veritabanı doğrulanıyor…</p>
            <div role="progressbar" aria-label="ARKALI başlatılıyor" className="mt-6 h-1.5 overflow-hidden rounded-full bg-slate-800"><div className="h-full w-2/3 animate-pulse rounded-full bg-emerald-400" /></div>
          </>
        ) : (
          <>
            <h1 className="text-xl font-semibold">Command Center başlatılamadı</h1>
            <p className="mt-2 text-sm text-slate-400">Yerel ARKALI backend’ine ulaşılamıyor. Başka bir uygulamanın 8000 portunu kullanmadığını kontrol edip yeniden deneyin.</p>
            <button type="button" onClick={() => setAttempt((value) => value + 1)} className="mt-6 rounded-lg bg-emerald-400 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-emerald-300">Yeniden dene</button>
          </>
        )}
      </section>
    </main>
  );
}
