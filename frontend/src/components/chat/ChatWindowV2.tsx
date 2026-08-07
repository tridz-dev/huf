import { ChatWindowHeader } from "./ChatWindowHeader";
import { ChatMessageList } from "./ChatMessageList";
import type { ArtifactPaneTarget } from "./useArtifactPane";
import type { ArtifactListItem } from "@/services/artifactPanelApi";

interface ChatWindowProps {
    chatId?: string | null;
    onConversationCreated?: (conversationId: string, agentName?: string) => void;
    onToggleSidebar?: () => void;
    artifactPaneOpen?: boolean;
    onToggleArtifactPane?: () => void;
    artifacts?: ArtifactListItem[];
    onOpenArtifact?: (target: ArtifactPaneTarget) => void;
    activeArtifactName?: string;
}

export default function ChatWindow({
    chatId: chatIdProp,
    onConversationCreated,
    onToggleSidebar,
    artifactPaneOpen,
    onToggleArtifactPane,
    artifacts,
    onOpenArtifact,
    activeArtifactName,
}: ChatWindowProps) {
    return (
        <div className="w-full h-full flex flex-col overflow-hidden bg-background">
            <ChatWindowHeader
                chatId={chatIdProp}
                onToggleSidebar={onToggleSidebar}
                artifactPaneOpen={artifactPaneOpen}
                onToggleArtifactPane={onToggleArtifactPane}
            />
            <ChatMessageList
                chatId={chatIdProp}
                onConversationCreated={onConversationCreated}
                artifacts={artifacts}
                onOpenArtifact={onOpenArtifact}
                activeArtifactName={activeArtifactName}
            />
        </div>
    );
}
