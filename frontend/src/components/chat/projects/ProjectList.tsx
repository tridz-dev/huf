// A7: Row list of the user's HUF Projects for the Projects landing page.
// Pure presentation - ChatProjectsPage owns fetching/loading/empty-state
// and only hands this component a populated array to render.

import { Folder } from 'lucide-react';
import { formatTimeAgo } from '@/utils/time';
import type { HufProject } from '@/services/projectApi';

export interface ProjectListProps {
  projects: HufProject[];
  onSelect: (project: HufProject) => void;
}

export function ProjectList({ projects, onSelect }: ProjectListProps) {
  return (
    <ul className="flex flex-col divide-y divide-line rounded-[12px] border border-line bg-panel overflow-hidden">
      {projects.map((project) => (
        <li key={project.name}>
          <button
            type="button"
            onClick={() => onSelect(project)}
            className="flex w-full items-start gap-3 px-4 py-3.5 text-left transition-colors hover:bg-paper-deep focus-visible:outline-none focus-visible:bg-paper-deep"
          >
            <Folder className="mt-0.5 h-4 w-4 shrink-0 text-steel-soft" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-[14px] font-medium text-ink">{project.project_name}</p>
              {project.description && (
                <p className="truncate text-[13px] text-steel mt-0.5">{project.description}</p>
              )}
            </div>
            {project.last_activity && (
              <span className="shrink-0 text-[12px] text-steel-soft whitespace-nowrap mt-0.5">
                Active {formatTimeAgo(project.last_activity)}
              </span>
            )}
          </button>
        </li>
      ))}
    </ul>
  );
}
