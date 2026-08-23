import { useState, useCallback, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ChatShellFrame } from "@/components/chat/rail/ChatShellFrame";
import ChatWindow from "@/components/chat/ChatWindowV2";
import { ArtifactPreviewPane } from "@/components/chat/artifacts/ArtifactPreviewPane";
import { useArtifactPane } from "@/components/chat/useArtifactPane";
import { useConversationArtifacts } from "@/components/chat/useConversationArtifacts";
import { useChatSocket, type OpenArtifactPaneEvent } from "@/hooks/useChatSocket";
import { useIsMobile } from "@/hooks/use-mobile";
import { ConversationAnalyticsPane } from "@/components/chat/analytics/ConversationAnalyticsPane";
import { useConversationAnalyticsPane } from "@/components/chat/analytics/useConversationAnalyticsPane";
import { RightPaneTabStrip, type RightPaneTab } from "@/components/chat/analytics/RightPaneTabStrip";

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
    const analyticsPane = useConversationAnalyticsPane();
    // Which of the two right-pane tenants is currently on screen. Both can be
    // "open" (loaded, data fetched) at once — see useConversationAnalyticsPane
    // and useArtifactPane — but the slot only ever shows one at a time. This
    // tracks the user's last choice so switching tabs doesn't lose state.
    const [visibleRightPane, setVisibleRightPane] = useState<RightPaneTab>("artifact");
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
        if (artifactPane.isOpen && visibleRightPane === "artifact") {
            artifactPane.close();
            if (analyticsPane.isOpen) setVisibleRightPane("analytics");
            return;
        }
        if (!artifactPane.isOpen) {
            const first = conversationArtifacts[0];
            if (first) {
                artifactPane.open({ name: first.name, title: first.title, artifact_type: first.artifact_type });
            } else {
                return;
            }
        }
        setVisibleRightPane("artifact");
    }, [artifactPane.isOpen, artifactPane.close, artifactPane.open, analyticsPane.isOpen, conversationArtifacts, visibleRightPane]);

    // Sibling of handleToggleArtifactPane: toggles the conversation analytics
    // pane on/off, switching the shared right-pane slot to show it. Unlike
    // the artifact toggle, analytics has no "pick the first item" step - it
    // always describes the whole open conversation.
    const handleToggleAnalyticsPane = useCallback(() => {
        if (analyticsPane.isOpen && visibleRightPane === "analytics") {
            analyticsPane.close();
            if (artifactPane.isOpen) setVisibleRightPane("artifact");
            return;
        }
        analyticsPane.open();
        setVisibleRightPane("analytics");
    }, [analyticsPane.isOpen, analyticsPane.close, analyticsPane.open, artifactPane.isOpen, visibleRightPane]);

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

    // The right-pane slot has two independent tenants that can each be
    // loaded ("open") at once but only one is ever on screen: the artifact
    // preview and the conversation analytics pane. When both are open, a
    // thin RightPaneTabStrip is mounted above whichever one is visible so
    // the user can switch without losing the other's state; when only one
    // is open, no strip renders at all (see RightPaneTabStrip.tsx).
    const artifactAvailable = artifactPane.isOpen;
    const analyticsAvailable = analyticsPane.isOpen;
    const effectiveVisiblePane: RightPaneTab =
        visibleRightPane === "artifact" && artifactAvailable
            ? "artifact"
            : visibleRightPane === "analytics" && analyticsAvailable
              ? "analytics"
              : artifactAvailable
                ? "artifact"
                : "analytics";
    const rightPaneVisible = !isMobile && (artifactAvailable || analyticsAvailable);
    const showRightPaneTabs = artifactAvailable && analyticsAvailable;

    // The artifact/analytics pane renders as a third column, a sibling of
    // the rail and the chat window - passed to ChatShellFrame as `rightPane`
    // so the shared shell doesn't swallow it into the middle flex area.
    // Produced files surface inline via the transcript's Outputs card (see
    // OutputsCard.tsx, spec section 28.2) instead of a permanent right-hand
    // list. Hidden on mobile to avoid crowding the chat window.
    return (
        <ChatShellFrame
            sidebarOpen={sidebarOpen}
            onToggleSidebar={toggleSidebar}
            rightPane={
                rightPaneVisible ? (
                    <div className="flex h-full flex-col">
                        {showRightPaneTabs && (
                            <RightPaneTabStrip
                                active={effectiveVisiblePane}
                                onSelect={setVisibleRightPane}
                                width={artifactPane.width}
                            />
                        )}
                        {effectiveVisiblePane === "artifact" ? (
                            <ArtifactPreviewPane
                                artifact={artifactPane.currentArtifact}
                                onClose={artifactPane.close}
                                width={artifactPane.width}
                                onWidthChange={artifactPane.setWidth}
                                artifacts={conversationArtifacts}
                                onSelectArtifact={artifactPane.open}
                            />
                        ) : (
                            <ConversationAnalyticsPane
                                conversationId={chatId}
                                onClose={analyticsPane.close}
                                width={artifactPane.width}
                                onWidthChange={artifactPane.setWidth}
                            />
                        )}
                    </div>
                ) : null
            }
        >
            <ChatWindow
                chatId={chatId}
                onConversationCreated={handleConversationCreated}
                onToggleSidebar={isMobile ? toggleSidebar : undefined}
                railCollapsed={!sidebarOpen}
                onExpandRail={toggleSidebar}
                artifactPaneOpen={artifactAvailable}
                onToggleArtifactPane={
                    !isMobile && (artifactAvailable || conversationArtifacts.length > 0)
                        ? handleToggleArtifactPane
                        : undefined
                }
                artifacts={conversationArtifacts}
                onOpenArtifact={artifactPane.open}
                activeArtifactName={artifactPane.currentArtifact?.name}
                analyticsPaneOpen={analyticsAvailable}
                onToggleAnalyticsPane={!isMobile && chatId ? handleToggleAnalyticsPane : undefined}
            />
        </ChatShellFrame>
    );
}
