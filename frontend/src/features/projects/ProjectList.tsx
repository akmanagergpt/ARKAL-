import type { ProjectResponse } from '@/api/contracts';
import { Button, Callout, Panel, Spinner, StateBadge } from '@/components/ui';

export function ProjectList({
  projects,
  selectedId,
  loading,
  failure,
  onSelect,
  onReload,
}: {
  projects: readonly ProjectResponse[];
  selectedId: string | null;
  loading: boolean;
  failure: { code: string; message: string } | null;
  onSelect: (projectId: string) => void;
  onReload: () => void;
}) {
  return (
    <Panel
      title="Projects"
      actions={
        <Button onClick={onReload} disabled={loading}>
          Refresh
        </Button>
      }
    >
      {loading ? (
        <p className="py-6 text-center">
          <Spinner label="Loading the project registry…" />
        </p>
      ) : failure !== null ? (
        <Callout tone="error" title="The registry could not be read">
          <p>{failure.message}</p>
          <p className="mt-1 font-mono text-xs opacity-80">{failure.code}</p>
        </Callout>
      ) : projects.length === 0 ? (
        <div className="py-6 text-center">
          <p className="text-sm font-medium text-slate-800">No projects yet</p>
          <p className="mt-1 text-sm text-slate-500">
            Register the first project to begin. Nothing is stored in this browser —
            the registry lives in the ARKALI database.
          </p>
        </div>
      ) : (
        <ul className="divide-y divide-slate-200">
          {projects.map((project) => {
            const isSelected = project.project_id === selectedId;
            return (
              <li key={project.project_id}>
                <button
                  type="button"
                  aria-current={isSelected ? 'true' : undefined}
                  onClick={() => onSelect(project.project_id)}
                  className={`flex w-full flex-wrap items-center justify-between gap-2 px-2 py-3 text-left transition-colors hover:bg-slate-50 ${
                    isSelected ? 'bg-slate-100' : ''
                  }`}
                >
                  <span>
                    <span className="block text-sm font-medium text-slate-900">
                      {project.name}
                    </span>
                    <span className="block font-mono text-xs text-slate-500">
                      {project.project_id}
                    </span>
                  </span>
                  <StateBadge state={project.lifecycle_state} />
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}
