// A7: Projects landing page - the main-area index for /chat/projects.
// Lists the user's HUF Projects, offers a "+ Project" create action, and
// navigates into a project's detail route (A8) on row click. This is a
// content page inside the existing chat shell, not a sidebar tree - the
// global rail stays exactly as-is (ChatShellFrame renders it unchanged).

import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Folder, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/dashboard/views/EmptyState';
import { ChatShellFrame } from '@/components/chat/rail/ChatShellFrame';
import { ProjectList } from '@/components/chat/projects/ProjectList';
import { CreateProjectDialog } from '@/components/chat/projects/CreateProjectDialog';
import { listProjects, type HufProject } from '@/services/projectApi';

export function ChatProjectsPage() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<HufProject[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const result = await listProjects();
      setProjects(result);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleSelect = (project: HufProject) => {
    navigate(`/chat/projects/${project.name}`);
  };

  const handleCreated = async (project: HufProject) => {
    await refresh();
    navigate(`/chat/projects/${project.name}`);
  };

  return (
    <ChatShellFrame>
      <div className="flex h-full w-full flex-col overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-5 border-b border-line">
          <h1 className="text-[16px] font-medium text-ink">Projects</h1>
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4" />
            Project
          </Button>
        </div>

        <div className="flex-1 px-6 py-5">
          {loading ? (
            <p className="text-[13px] text-steel-soft">Loading projects...</p>
          ) : projects.length === 0 ? (
            <div className="flex h-full items-center justify-center">
              <EmptyState
                variant="create"
                icon={Folder}
                title="No projects yet"
                description="Projects group related conversations so they share context and files."
                action={{
                  label: '+ Project',
                  onClick: () => setCreateOpen(true),
                }}
              />
            </div>
          ) : (
            <div className="mx-auto max-w-[720px]">
              <ProjectList projects={projects} onSelect={handleSelect} />
            </div>
          )}
        </div>
      </div>

      <CreateProjectDialog open={createOpen} onOpenChange={setCreateOpen} onCreated={handleCreated} />
    </ChatShellFrame>
  );
}
