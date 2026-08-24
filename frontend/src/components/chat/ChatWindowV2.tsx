import { ChatWindowHeader } from "./ChatWindowHeader";
import { ChatMessageList } from "./ChatMessageList";
import type { ArtifactPaneTarget } from "./useArtifactPane";
import type { ArtifactListItem } from "@/services/artifactPanelApi";

interface ChatWindowProps {
    chatId?: string | null;
    onConversationCreated?: (conversationId: string, agentName?: string) => void;
    onToggleSidebar?: () => void;
    /** Whether the shared chat rail is currently collapsed - spec 28.5 puts
     * the rail's expand control as the first item in the header row instead
     * of a floating button, so ChatWindowHeader needs to know the rail's
     * state to render it. */
    railCollapsed?: boolean;
    /** Expands the rail when railCollapsed is true. */
    onExpandRail?: () => void;
    artifactPaneOpen?: boolean;
    onToggleArtifactPane?: () => void;
    artifacts?: ArtifactListItem[];
    onOpenArtifact?: (target: ArtifactPaneTarget) => void;
    activeArtifactName?: string;
    /** Whether the right-docked conversation analytics pane is currently open. */
    analyticsPaneOpen?: boolean;
    /** Toggles the analytics pane. Sibling of onToggleArtifactPane - the
     * header only renders its toggle button when this is provided. */
    onToggleAnalyticsPane?: () => void;
}

export default function ChatWindow({
    chatId: chatIdProp,
    onConversationCreated,
    onToggleSidebar,
    railCollapsed,
    onExpandRail,
    artifactPaneOpen,
    onToggleArtifactPane,
    artifacts,
    onOpenArtifact,
    activeArtifactName,
    analyticsPaneOpen,
    onToggleAnalyticsPane,
}: ChatWindowProps) {
    return (
        <div className="w-full h-full flex flex-col overflow-hidden bg-background">
            <ChatWindowHeader
                chatId={chatIdProp}
                onToggleSidebar={onToggleSidebar}
                railCollapsed={railCollapsed}
                onExpandRail={onExpandRail}
                artifactPaneOpen={artifactPaneOpen}
                onToggleArtifactPane={onToggleArtifactPane}
                analyticsPaneOpen={analyticsPaneOpen}
                onToggleAnalyticsPane={onToggleAnalyticsPane}
            />
            <ChatMessageList
                chatId={chatIdProp}
                onConversationCreated={onConversationCreated}
                artifacts={artifacts}
                onOpenArtifact={onOpenArtifact}
                activeArtifactName={activeArtifactName}
                artifactPaneOpen={artifactPaneOpen}
            />
        </div>
    );
}
