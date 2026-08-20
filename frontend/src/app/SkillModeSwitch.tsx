export type SkillMode = 'beginner' | 'professional' | 'expert';

const MODES: readonly { id: SkillMode; label: string; hint: string }[] = [
  { id: 'beginner', label: 'Başlangıç', hint: 'Sade ve yönlendirilmiş görünüm' },
  { id: 'professional', label: 'Profesyonel', hint: 'Planlama ve yönetim ayrıntıları' },
  { id: 'expert', label: 'Uzman', hint: 'Workflow ve teknik araçlar' },
];

export function SkillModeSwitch({ mode, onChange }: { mode: SkillMode; onChange: (mode: SkillMode) => void }) {
  return <fieldset className="flex items-center gap-1" aria-label="Deneyim düzeyi">
    <legend className="sr-only">Deneyim düzeyi</legend>
    {MODES.map((item) => <button key={item.id} type="button" aria-pressed={mode === item.id} title={item.hint} onClick={() => onChange(item.id)} className={`rounded-md px-2.5 py-1.5 text-xs font-medium transition ${mode === item.id ? 'bg-slate-950 text-white' : 'text-slate-600 hover:bg-slate-100'}`}>{item.label}</button>)}
  </fieldset>;
}
