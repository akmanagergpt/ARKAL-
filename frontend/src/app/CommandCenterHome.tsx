import type { ArkaliApiClient } from '@/api/client';
import { NewApplicationIntake } from '@/features/factory/NewApplicationIntake';
import type { AreaId } from './areas';
import type { SkillMode } from './SkillModeSwitch';

export function CommandCenterHome({ navigate, mode, client }: { navigate: (area: AreaId) => void; mode: SkillMode; client: ArkaliApiClient }) {
  return <div className="arkali-home">
    <section className="arkali-hero">
      <div className="arkali-hero-copy">
        <div className="arkali-eyebrow"><span className="arkali-status-dot" /> LOCAL-FIRST INTELLIGENCE</div>
        <h1>Ne üretmek istiyorsunuz?</h1>
        <p>ARKALI ile fikrinizi doğal dille anlatın. Sistem isteği anlamlandırır, gerçek bir üretim işine dönüştürür ve sonucu doğrulanabilir şekilde sunar.</p>
      </div>
      <div className="arkali-hero-orbit" aria-hidden="true"><span /><span /><span /><b>A</b></div>
    </section>

    <NewApplicationIntake client={client} showTechnical={mode === 'expert'} />

    <section className="arkali-quick-grid" aria-label="Hızlı çalışma alanları">
      <button type="button" onClick={() => navigate('products')}><span className="arkali-quick-icon">◈</span><div><strong>Uygulamalarım</strong><small>Gerçek proje ve sürümler</small></div><span>→</span></button>
      <button type="button" onClick={() => navigate('factory')}><span className="arkali-quick-icon">✦</span><div><strong>AI Software Factory</strong><small>Üretim geçmişi ve adaylar</small></div><span>→</span></button>
      <button type="button" onClick={() => navigate('operations')}><span className="arkali-quick-icon">◌</span><div><strong>Operasyonlar</strong><small>Canlı sistem durumu</small></div><span>→</span></button>
      {mode === 'expert' ? <button type="button" onClick={() => navigate('workflow')}><span className="arkali-quick-icon">⌘</span><div><strong>Workflow Studio</strong><small>Gelişmiş akış tasarımı</small></div><span>→</span></button> : null}
    </section>
  </div>;
}
