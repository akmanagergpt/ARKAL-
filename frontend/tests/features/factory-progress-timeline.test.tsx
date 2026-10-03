import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { FactoryProgressTimeline } from '@/features/factory/FactoryProgressTimeline';

describe('FactoryProgressTimeline', () => {
  it('renders only real durable checkpoints and translates real stage names', () => {
    render(
      <FactoryProgressTimeline
        showTechnical={false}
        checkpoints={[
          { sequence: 1, payload: { phase: 'claimed' }, recorded_at: '2026-10-04T00:00:00Z' },
          { sequence: 2, payload: { phase: 'generating' }, recorded_at: '2026-10-04T00:00:01Z' },
          {
            sequence: 3,
            payload: { phase: 'stage_started', candidate_id: 'factory-goal-1', stage: 'backend_contract' },
            recorded_at: '2026-10-04T00:00:02Z',
          },
          {
            sequence: 4,
            payload: { phase: 'stage_started', candidate_id: 'factory-goal-1', stage: 'backend_schema' },
            recorded_at: '2026-10-04T00:00:03Z',
          },
        ]}
      />,
    );

    expect(screen.getByText('Üretim işi worker tarafından alındı')).toBeInTheDocument();
    expect(screen.getByText('İzole ürün çalışma alanı hazırlandı')).toBeInTheDocument();
    expect(screen.getByText('Veri ve API sözleşmesi hazırlanıyor')).toBeInTheDocument();
    expect(screen.getByText('Veritabanı şeması oluşturuluyor')).toBeInTheDocument();
    expect(screen.getByText(/animasyon değildir/)).toBeInTheDocument();
    expect(screen.queryByText('Backend uygulanıyor')).not.toBeInTheDocument();
  });

  it('shows the exact stage identity only in technical mode', () => {
    render(
      <FactoryProgressTimeline
        showTechnical
        checkpoints={[
          {
            sequence: 7,
            payload: { phase: 'stage_started', stage: 'frontend_ui' },
            recorded_at: '2026-10-04T00:00:07Z',
          },
        ]}
      />,
    );

    expect(screen.getByText(/#7 · frontend_ui/)).toBeInTheDocument();
  });
});
