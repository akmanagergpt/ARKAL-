import type { AreaId } from './areas';
import type { SkillMode } from './SkillModeSwitch';

export function CommandCenterHome({ navigate, mode }: { navigate: (area: AreaId) => void; mode: SkillMode }) {
  return <div className="space-y-6">
    <section className="overflow-hidden rounded-2xl bg-slate-950 px-6 py-8 text-white shadow-sm sm:px-8">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-sky-300">Command Center</p>
      <h1 className="mt-3 max-w-2xl text-3xl font-semibold tracking-tight sm:text-4xl">Bugün ne üzerinde çalışmak istiyorsunuz?</h1>
      <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-300">{mode === 'expert' ? 'Projelerinizi yönetin veya gelişmiş bir iş akışı oluşturun. Yalnızca gerçek ARKALI servislerine bağlı alanlar kullanılabilir.' : 'Uygulamalarınızı buradan yönetin. Yalnızca gerçek ARKALI servislerine bağlı alanlar kullanılabilir.'}</p>
      <div className="mt-6 flex flex-wrap gap-3">
        <button className="rounded-lg bg-white px-4 py-2.5 text-sm font-semibold text-slate-950 hover:bg-sky-50" onClick={() => navigate('products')}>Projeleri aç</button>
        {mode === 'expert' ? <button className="rounded-lg border border-slate-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-slate-800" onClick={() => navigate('workflow')}>Gelişmiş stüdyoyu aç</button> : null}
      </div>
    </section>
    <section aria-labelledby="available-heading">
      <h2 id="available-heading" className="text-lg font-semibold text-slate-950">Kullanılabilir çalışma alanları</h2>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <button onClick={() => navigate('products')} className="rounded-xl border border-slate-200 bg-white p-5 text-left shadow-sm transition hover:border-sky-300 hover:shadow-md"><span className="text-sm font-semibold text-slate-950">Yönetilen Ürünler</span><span className="mt-1 block text-sm text-slate-600">Gerçek proje kayıtlarını görüntüleyin ve yönetin.</span></button>
        <button onClick={() => navigate('operations')} className="rounded-xl border border-slate-200 bg-white p-5 text-left shadow-sm transition hover:border-sky-300 hover:shadow-md"><span className="text-sm font-semibold text-slate-950">Operasyonlar</span><span className="mt-1 block text-sm text-slate-600">Sistem ve çalışma durumunu canlı olarak izleyin.</span></button>
        {mode === 'expert' ? <button onClick={() => navigate('workflow')} className="rounded-xl border border-slate-200 bg-white p-5 text-left shadow-sm transition hover:border-sky-300 hover:shadow-md"><span className="text-sm font-semibold text-slate-950">Workflow Studio</span><span className="mt-1 block text-sm text-slate-600">İş akışlarını tasarlayın, yayınlayın ve çalıştırın.</span></button> : null}
      </div>
    </section>
  </div>;
}
