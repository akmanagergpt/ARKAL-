export type AreaId = 'command' | 'factory' | 'products' | 'workflow' | 'team' | 'providers' | 'operations' | 'knowledge' | 'code-intelligence' | 'evolution' | 'extensions' | 'security' | 'release' | 'diagnostics';

export interface CommandArea { readonly id: AreaId; readonly label: string; readonly description: string; readonly available: boolean; }

/** Canonical Command Center names plus this frontend's real surface inventory. */
export const COMMAND_AREAS: readonly CommandArea[] = [
  { id: 'command', label: 'Ana Sayfa', description: 'Genel bakış ve sonraki adımlar', available: true },
  { id: 'factory', label: 'AI Software Factory', description: 'Üretim akışları', available: false },
  { id: 'products', label: 'Yönetilen Ürünler', description: 'Projeler ve ürün kayıtları', available: true },
  { id: 'workflow', label: 'Workflow Studio', description: 'Gelişmiş iş akışı tasarımı', available: true },
  { id: 'team', label: 'AI Ekibi', description: 'Ajanlar ve görevler', available: false },
  { id: 'providers', label: 'Sağlayıcılar ve Modeller', description: 'Model kullanılabilirliği', available: false },
  { id: 'operations', label: 'Operasyonlar', description: 'Sistem ve çalışma durumu', available: true },
  { id: 'knowledge', label: 'Bilgi', description: 'Doğrulanmış bilgi ve bileşenler', available: false },
  { id: 'code-intelligence', label: 'Kod Zekâsı', description: 'Kod görünümü ve analizler', available: false },
  { id: 'evolution', label: 'Evrim', description: 'Ürün ve çekirdek evrimi', available: false },
  { id: 'extensions', label: 'Uzantılar', description: 'Eklentiler ve entegrasyonlar', available: false },
  { id: 'security', label: 'Güvenlik', description: 'Politikalar ve güvenlik bulguları', available: false },
  { id: 'release', label: 'Sürüm ve Dağıtım', description: 'Sürüm hazırlığı ve teslimat', available: false },
  { id: 'diagnostics', label: 'Tanılama', description: 'Teknik inceleme araçları', available: false },
] as const;
