import { useState } from 'react';

import { Button, Callout, Field, Panel } from '@/components/ui';

/**
 * Derives a real, registry-submittable identifier from the user's own real
 * name input — never a second identity authority. This is only ever a
 * DEFAULT VALUE for the same required `project_id` field the technical form
 * already sends to the same real `POST /api/projects`; the registry (never
 * this function) still decides whether the derived string is acceptable,
 * exactly the same as any identifier a technical user typed by hand. Kept
 * deterministic from the name plus a real timestamp so two beginners
 * registering "Kitap Kulübü" the same second still get different real ids,
 * without inventing a second uniqueness rule of its own.
 */
function deriveProjectId(name: string): string {
  const slug = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  const suffix = Date.now().toString(36);
  return slug === '' ? `uygulama-${suffix}` : `${slug}-${suffix}`;
}

/**
 * Registration form.
 *
 * The only check made here is that both fields carry a non-blank value, which
 * is a courtesy so the user is not made to wait for a round trip to learn they
 * left a box empty. Identity rules — length, uniqueness, character set — belong
 * to the registry, and this form never pre-judges them.
 *
 * `showTechnical` (default true, so an existing caller predating this prop
 * is unaffected): when false, the raw "Project identifier" field is hidden
 * and `deriveProjectId` supplies it instead — a beginner names their own
 * application in their own words and never has to invent a stable technical
 * key by hand, per the Command Center's own beginner-mode contract. The
 * real registry call, and the real refusal path if it declines the
 * derived id, are identical either way.
 */
export function CreateProjectForm({
  submitting,
  onCreate,
  showTechnical = true,
}: {
  submitting: boolean;
  onCreate: (projectId: string, name: string) => Promise<void>;
  showTechnical?: boolean;
}) {
  const [projectId, setProjectId] = useState('');
  const [name, setName] = useState('');
  const [invalid, setInvalid] = useState<string | null>(null);

  const submit = (): void => {
    const trimmedName = name.trim();
    if (trimmedName === '' || (showTechnical && projectId.trim() === '')) {
      setInvalid(
        showTechnical
          ? 'Bir uygulama kimliği ve bir ad girmelisiniz.'
          : 'Bir ad girmelisiniz.',
      );
      return;
    }
    setInvalid(null);
    const resolvedId = showTechnical ? projectId.trim() : deriveProjectId(trimmedName);
    void onCreate(resolvedId, trimmedName).then(() => {
      setProjectId('');
      setName('');
    });
  };

  return (
    <Panel title={showTechnical ? 'Proje kaydı oluştur' : 'Yeni uygulama ekle'}>
      <form
        className="flex flex-col gap-4"
        // The browser's own validation bubble is suppressed so the refusal is
        // presented in the same place, and the same way, as a backend refusal.
        // The fields stay `required` for assistive technology.
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        {showTechnical ? (
          <Field
            id="new-project-id"
            label="Proje tanımlayıcısı"
            value={projectId}
            onChange={setProjectId}
            disabled={submitting}
            required
            hint="Proje için sabit kimlik. Bu değerin kabul edilip edilmeyeceğine kayıt sistemi karar verir."
          />
        ) : null}
        <Field
          id="new-project-name"
          label={showTechnical ? 'Proje adı' : 'Uygulama adı'}
          value={name}
          onChange={setName}
          disabled={submitting}
          required
        />
        {invalid === null ? null : <Callout tone="error" title={invalid} />}
        <div>
          <Button type="submit" variant="primary" busy={submitting}>
            {submitting
              ? (showTechnical ? 'Kaydediliyor…' : 'Ekleniyor…')
              : (showTechnical ? 'Projeyi kaydet' : 'Uygulamayı ekle')}
          </Button>
        </div>
      </form>
    </Panel>
  );
}
