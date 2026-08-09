/**
 * View state for the Project Registry page.
 *
 * THIS IS A VIEW CACHE, NOT A REGISTRY. Everything it holds was returned by the
 * backend and is replaced by the backend's answer after every mutation. It
 * derives no project, invents no lifecycle state and never reports a mutation
 * as successful on its own authority — a create or a transition is successful
 * only because the API said so and returned the resulting record.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';

import { ApiRefusal, ApiUnavailable, type ArkaliApiClient } from '@/api/client';
import type {
  ProjectDetailResponse,
  ProjectResponse,
} from '@/api/contracts';

export interface Failure {
  /** Backend error code where one was given; `UNREACHABLE` for transport. */
  readonly code: string;
  readonly message: string;
}

export interface RegistryState {
  readonly projects: readonly ProjectResponse[];
  readonly selected: ProjectDetailResponse | null;
  readonly lifecycleStates: readonly string[];
  readonly loadingList: boolean;
  readonly loadingDetail: boolean;
  readonly submitting: boolean;
  readonly listFailure: Failure | null;
  readonly actionFailure: Failure | null;
  readonly notice: string | null;
}

export interface RegistryActions {
  select: (projectId: string) => void;
  reload: () => void;
  createProject: (projectId: string, name: string) => Promise<void>;
  requestTransition: (projectId: string, target: string) => Promise<void>;
  createRevision: (projectId: string, revisionId: string) => Promise<void>;
  dismissNotice: () => void;
}

/** Turn any thrown value into something presentable, losing no backend detail. */
function asFailure(error: unknown): Failure {
  if (error instanceof ApiRefusal) {
    return { code: error.code, message: error.message };
  }
  if (error instanceof ApiUnavailable) {
    return { code: 'UNREACHABLE', message: error.message };
  }
  return { code: 'UNEXPECTED', message: 'An unexpected error occurred.' };
}

export function useProjectRegistry(client: ArkaliApiClient): RegistryState & RegistryActions {
  const [projects, setProjects] = useState<readonly ProjectResponse[]>([]);
  const [selected, setSelected] = useState<ProjectDetailResponse | null>(null);
  const [lifecycleStates, setLifecycleStates] = useState<readonly string[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [listFailure, setListFailure] = useState<Failure | null>(null);
  const [actionFailure, setActionFailure] = useState<Failure | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const reload = useCallback(() => {
    let cancelled = false;
    setLoadingList(true);
    setListFailure(null);
    client
      .listProjects()
      .then((page) => {
        if (!cancelled) {
          setProjects(page.projects);
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setProjects([]);
          setListFailure(asFailure(error));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingList(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [client]);

  useEffect(() => reload(), [reload]);

  // The vocabulary is fetched, never declared. A build that could not reach the
  // backend simply offers no lifecycle action, which is honest; a hard-coded
  // fallback list would be this module claiming to know the machine.
  useEffect(() => {
    let cancelled = false;
    client
      .lifecycleStates()
      .then((machine) => {
        if (!cancelled) {
          setLifecycleStates(machine.states);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setLifecycleStates([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [client]);

  const select = useCallback(
    (projectId: string) => {
      setLoadingDetail(true);
      setActionFailure(null);
      client
        .getProject(projectId)
        .then(setSelected)
        .catch((error: unknown) => {
          setSelected(null);
          setActionFailure(asFailure(error));
        })
        .finally(() => setLoadingDetail(false));
    },
    [client],
  );

  /** Run a mutation, then take the backend's answer as the new truth. */
  const mutate = useCallback(
    async (
      operation: () => Promise<ProjectDetailResponse>,
      success: (detail: ProjectDetailResponse) => string,
    ): Promise<void> => {
      setSubmitting(true);
      setActionFailure(null);
      setNotice(null);
      try {
        const detail = await operation();
        setSelected(detail);
        setNotice(success(detail));
        const page = await client.listProjects();
        setProjects(page.projects);
      } catch (error: unknown) {
        setActionFailure(asFailure(error));
      } finally {
        setSubmitting(false);
      }
    },
    [client],
  );

  const createProject = useCallback(
    (projectId: string, name: string) =>
      mutate(
        () => client.createProject({ project_id: projectId, name }),
        (detail) => `Project ${detail.project_id} registered in ${detail.lifecycle_state}.`,
      ),
    [client, mutate],
  );

  const requestTransition = useCallback(
    (projectId: string, target: string) =>
      mutate(
        () => client.transitionProject(projectId, { target }),
        (detail) => `${detail.project_id} is now ${detail.lifecycle_state}.`,
      ),
    [client, mutate],
  );

  const createRevision = useCallback(
    (projectId: string, revisionId: string) =>
      mutate(
        () => client.createRevision(projectId, { revision_id: revisionId, provenance_ref: null }),
        (detail) => `Revision ${revisionId} recorded for ${detail.project_id}.`,
      ),
    [client, mutate],
  );

  const dismissNotice = useCallback(() => setNotice(null), []);

  return useMemo(
    () => ({
      projects,
      selected,
      lifecycleStates,
      loadingList,
      loadingDetail,
      submitting,
      listFailure,
      actionFailure,
      notice,
      select,
      reload,
      createProject,
      requestTransition,
      createRevision,
      dismissNotice,
    }),
    [
      projects,
      selected,
      lifecycleStates,
      loadingList,
      loadingDetail,
      submitting,
      listFailure,
      actionFailure,
      notice,
      select,
      reload,
      createProject,
      requestTransition,
      createRevision,
      dismissNotice,
    ],
  );
}
