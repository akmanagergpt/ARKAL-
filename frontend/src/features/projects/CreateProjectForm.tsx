import { useState } from 'react';

import { Button, Callout, Field, Panel } from '@/components/ui';

/**
 * Registration form.
 *
 * The only check made here is that both fields carry a non-blank value, which
 * is a courtesy so the user is not made to wait for a round trip to learn they
 * left a box empty. Identity rules — length, uniqueness, character set — belong
 * to the registry, and this form never pre-judges them.
 */
export function CreateProjectForm({
  submitting,
  onCreate,
}: {
  submitting: boolean;
  onCreate: (projectId: string, name: string) => Promise<void>;
}) {
  const [projectId, setProjectId] = useState('');
  const [name, setName] = useState('');
  const [invalid, setInvalid] = useState<string | null>(null);

  const submit = (): void => {
    if (projectId.trim() === '' || name.trim() === '') {
      setInvalid('A project identifier and a name are both required.');
      return;
    }
    setInvalid(null);
    void onCreate(projectId.trim(), name.trim()).then(() => {
      setProjectId('');
      setName('');
    });
  };

  return (
    <Panel title="Register a project">
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
        <Field
          id="new-project-id"
          label="Project identifier"
          value={projectId}
          onChange={setProjectId}
          disabled={submitting}
          required
          hint="Stable identity for the project. The registry decides whether it is acceptable."
        />
        <Field
          id="new-project-name"
          label="Project name"
          value={name}
          onChange={setName}
          disabled={submitting}
          required
        />
        {invalid === null ? null : <Callout tone="error" title={invalid} />}
        <div>
          <Button type="submit" variant="primary" busy={submitting}>
            {submitting ? 'Registering…' : 'Register project'}
          </Button>
        </div>
      </form>
    </Panel>
  );
}
