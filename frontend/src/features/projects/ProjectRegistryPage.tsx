import type { ArkaliApiClient } from '@/api/client';
import { Callout, PageHeader } from '@/components/ui';

import { CreateProjectForm } from './CreateProjectForm';
import { ProjectDetail } from './ProjectDetail';
import { ProjectList } from './ProjectList';
import { useProjectRegistry } from './useProjectRegistry';

export function ProjectRegistryPage({ client, showTechnical }: { client: ArkaliApiClient; showTechnical: boolean }) {
  const registry = useProjectRegistry(client);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Projeler"
        subtitle="Projeleriniz doğrudan ARKALI kayıt sisteminden okunur. Durum ve sürüm bilgileri bu ekranda yeniden üretilmez."
      />

      {registry.notice === null ? null : (
        <Callout tone="success" title="Tamamlandı">
          <p>{registry.notice}</p>
        </Callout>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="flex flex-col gap-6">
          <ProjectList
            showTechnical={showTechnical}
            projects={registry.projects}
            selectedId={registry.selected?.project_id ?? null}
            loading={registry.loadingList}
            failure={registry.listFailure}
            onSelect={(projectId) => {
              registry.dismissNotice();
              registry.select(projectId);
            }}
            onReload={registry.reload}
          />
          <CreateProjectForm
            showTechnical={showTechnical}
            submitting={registry.submitting}
            onCreate={registry.createProject}
          />
        </div>
        <ProjectDetail
          showTechnical={showTechnical}
          client={client}
          project={registry.selected}
          lifecycleStates={registry.lifecycleStates}
          loading={registry.loadingDetail}
          submitting={registry.submitting}
          failure={registry.actionFailure}
          onTransition={registry.requestTransition}
          onCreateRevision={registry.createRevision}
        />
      </div>
    </div>
  );
}
