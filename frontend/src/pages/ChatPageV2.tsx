import { useState, useCallback, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ChatShellFrame } from "@/components/chat/rail/ChatShellFrame";
import ChatWindow from "@/components/chat/ChatWindowV2";
import { ArtifactPreviewPane } from "@/components/chat/artifacts/ArtifactPreviewPane";
import { useArtifactPane } from "@/components/chat/useArtifactPane";
import { useConversationArtifacts } from "@/components/chat/useConversationArtifacts";
import { useChatSocket, type OpenArtifactPaneEvent } from "@/hooks/useChatSocket";
import { useIsMobile } from "@/hooks/use-mobile";

export { ChatPage };
export default ChatPage;

function ChatPage() {
    const navigate = useNavigate();
    const { chatId: routeChatId } = useParams<{ chatId?: string }>();
    const chatId = routeChatId && routeChatId !== "new" ? routeChatId : null;

    const isMobile = useIsMobile();
    const [sidebarOpen, setSidebarOpen] = useState(true);
    const toggleSidebar = useCallback(() => setSidebarOpen((prev) => !prev), []);
    const artifactPane = useArtifactPane();
    const { artifacts: conversationArtifacts, refetch: refetchArtifacts } =
        useConversationArtifacts(chatId ?? undefined);

    // An agent tool (show_artifact) can open the preview pane on its own
    // initiative, via a `conversation:<id>` socket event - mirrors the
    // click-to-open path from ArtifactsPanel/ArtifactPreviewPane, just
    // triggered server-side instead of by the user.
    const handleOpenArtifactPane = useCallback(
        async (event: OpenArtifactPaneEvent) => {
            if (isMobile) return;
            if (event.conversation_id !== chatId) return;

            const known = conversationArtifacts.find((a) => a.name === event.artifact_id);
            if (known) {
                artifactPane.open({ name: known.name, title: known.title, artifact_type: known.artifact_type });
                return;
            }

            // Just-created artifact: the last-fetched list is stale. Re-fetch
            // once before giving up, rather than silently doing nothing.
            const refreshed = await refetchArtifacts();
            const found = refreshed.find((a) => a.name === event.artifact_id);
            if (found) {
                artifactPane.open({ name: found.name, title: found.title, artifact_type: found.artifact_type });
            }
        },
        [isMobile, chatId, conversationArtifacts, refetchArtifacts, artifactPane.open]
    );

    useChatSocket({
        conversationId: chatId,
        onOpenArtifactPane: handleOpenArtifactPane,
    });

    // Auto-close sidebar on mobile, auto-open on desktop
    useEffect(() => {
        setSidebarOpen(!isMobile);
    }, [isMobile]);

    // Close sidebar on mobile when a conversation is selected
    useEffect(() => {
        if (isMobile && chatId) {
            setSidebarOpen(false);
        }
    }, [isMobile, chatId]);

    // The rail, transcript, and artifact pane now coexist as three columns
    // (see design spec section 28.2) — the pane no longer forces the rail
    // closed, reversing the auto-collapse this effect used to do (previously
    // tracked as PLAN_PANE_UX.md item 4).

    // Toggles the artifact preview pane from the header glyph (spec 28): close
    // if open, or open the first available conversation artifact if closed.
    // ChatWindowHeader only renders the toggle when this callback is passed,
    // so callers that end up with no artifacts to show should not pass one -
    // see the conditional prop below.
    const handleToggleArtifactPane = useCallback(() => {
        if (artifactPane.isOpen) {
            artifactPane.close();
            return;
        }
        const first = conversationArtifacts[0];
        if (first) {
            artifactPane.open({ name: first.name, title: first.title, artifact_type: first.artifact_type });
        }
    }, [artifactPane.isOpen, artifactPane.close, artifactPane.open, conversationArtifacts]);

    const handleConversationCreated = useCallback(
        (conversationId: string, agentName?: string) => {
            const event = new CustomEvent("huf:conversation-created", {
                detail: { conversationId, agentName },
            });
            window.dispatchEvent(event);
            navigate(`/chat/${conversationId}`);
        },
        [navigate]
    );

    // The artifact pane renders as a third column, a sibling of the rail
    // and the chat window - passed to ChatShellFrame as `rightPane` so the
    // shared shell doesn't swallow it into the middle flex area. Produced
    // files surface inline via the transcript's Outputs card (see
    // OutputsCard.tsx, spec section 28.2) instead of a permanent right-hand
    // list. Hidden on mobile to avoid crowding the chat window.
    return (
        <ChatShellFrame
            sidebarOpen={sidebarOpen}
            onToggleSidebar={toggleSidebar}
            rightPane={
                !isMobile && artifactPane.isOpen ? (
                    <ArtifactPreviewPane
                        artifact={artifactPane.currentArtifact}
                        onClose={artifactPane.close}
                        width={artifactPane.width}
                        onWidthChange={artifactPane.setWidth}
                        artifacts={conversationArtifacts}
                        onSelectArtifact={artifactPane.open}
                    />
                ) : null
            }
        >
            <ChatWindow
                chatId={chatId}
                onConversationCreated={handleConversationCreated}
                onToggleSidebar={isMobile ? toggleSidebar : undefined}
                railCollapsed={!sidebarOpen}
                onExpandRail={toggleSidebar}
                artifactPaneOpen={artifactPane.isOpen}
                onToggleArtifactPane={
                    !isMobile && (artifactPane.isOpen || conversationArtifacts.length > 0)
                        ? handleToggleArtifactPane
                        : undefined
                }
                artifacts={conversationArtifacts}
                onOpenArtifact={artifactPane.open}
                activeArtifactName={artifactPane.currentArtifact?.name}
            />
        </ChatShellFrame>
    );
}
