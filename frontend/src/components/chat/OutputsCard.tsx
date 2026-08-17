/**
 * OutputsCard — spec section 28.2's in-transcript replacement for the old
 * permanent right-hand `ArtifactsPanel` list. Produced files now surface as a
 * card at the end of the transcript instead of a fixed w-80 column, so they
 * read as part of the conversation rather than a standing shell chrome.
 */
import type { LucideIcon } from 'lucide-react';
import { getArtifactIcon } from '@/components/chat/ArtifactsPanel';
import type { ArtifactPaneTarget } from '@/components/chat/useArtifactPane';
import type { ArtifactListItem } from '@/services/artifactPanelApi';
import { cn } from '@/lib/utils';

export interface OutputsCardProps {
  artifacts: ArtifactListItem[];
  onOpenArtifact: (target: ArtifactPaneTarget) => void;
  activeArtifactName?: string;
}

export function OutputsCard({ artifacts, onOpenArtifact, activeArtifactName }: OutputsCardProps) {
  if (artifacts.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-col gap-1 rounded-md border border-line p-2.5">
      <div className="flex items-center gap-2 text-[12px] text-steel">
        <span className="font-medium text-ink">Outputs</span>
        {artifacts.length}
      </div>
      {artifacts.map((artifact) => {
        const Icon: LucideIcon = getArtifactIcon(artifact.artifact_type);
        const isActive = artifact.name === activeArtifactName;
        return (
          <button
            key={artifact.name}
            type="button"
            onClick={() =>
              onOpenArtifact({
                name: artifact.name,
                title: artifact.title,
                artifact_type: artifact.artifact_type,
              })
            }
            className={cn(
              'flex h-chat-row w-full items-center gap-2 rounded-sm px-1 text-left text-[13px]',
              isActive ? 'bg-paper-deep text-ink' : 'text-steel'
            )}
          >
            <Icon className={cn('size-[15px] shrink-0', isActive ? 'text-steel' : 'text-steel-soft')} />
            <span className="truncate">{artifact.title || artifact.artifact_type}</span>
          </button>
        );
      })}
    </div>
  );
}

export default OutputsCard;
