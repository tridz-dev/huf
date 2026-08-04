import { useState, useCallback, useEffect, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import ChatListing from "@/components/chat/ChatListing";
import ChatWindow from "@/components/chat/ChatWindowV2";
import { ArtifactsPanel } from "@/components/chat/ArtifactsPanel";
import { ArtifactPreviewPane } from "@/components/chat/artifacts/ArtifactPreviewPane";
import { useArtifactPane } from "@/components/chat/useArtifactPane";
import { useConversationArtifacts } from "@/components/chat/useConversationArtifacts";
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
    const { artifacts: conversationArtifacts, loading: artifactsLoading } =
        useConversationArtifacts(chatId ?? undefined);

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

    // Auto-collapse the chat sidebar while the artifact preview pane is open,
    // and restore it to whatever it was before the pane opened — not
    // unconditionally re-opened, so a deliberately-collapsed sidebar stays
    // collapsed (see PLAN_PANE_UX.md item 4).
    const sidebarOpenBeforePaneRef = useRef<boolean | null>(null);
    useEffect(() => {
        if (artifactPane.isOpen) {
            if (sidebarOpenBeforePaneRef.current === null) {
                sidebarOpenBeforePaneRef.current = sidebarOpen;
            }
            if (sidebarOpen) {
                setSidebarOpen(false);
            }
        } else if (sidebarOpenBeforePaneRef.current !== null) {
            setSidebarOpen(sidebarOpenBeforePaneRef.current);
            sidebarOpenBeforePaneRef.current = null;
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [artifactPane.isOpen]);

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

    return (
        <section className="flex h-full overflow-hidden relative">
            {/* Sidebar - overlay on mobile, inline on desktop */}
            {isMobile ? (
                sidebarOpen && (
                    <div className="absolute inset-0 z-30 bg-sidebar">
                        <ChatListing onClose={toggleSidebar} />
                    </div>
                )
            ) : (
                <div
                    className={cn(
                        "shrink-0 transition-all duration-200 ease-in-out overflow-hidden",
                        sidebarOpen ? "w-80" : "w-0"
                    )}
                >
                    <div className="w-80 h-full">
                        <ChatListing />
                    </div>
                </div>
            )}

            {/* Chat window - always full width */}
            <div className="flex-1 min-w-0 min-h-0 h-full relative">
                {/* Desktop-only floating toggle */}
                {!isMobile && (
                    <Button
                        variant="ghost"
                        size="icon"
                        onClick={toggleSidebar}
                        className="absolute top-4 left-4 z-20 h-8 w-8 text-zinc-500 hover:text-zinc-900"
                    >
                        {sidebarOpen ? (
                            <PanelLeftClose className="h-4 w-4" />
                        ) : (
                            <PanelLeftOpen className="h-4 w-4" />
                        )}
                        <span className="sr-only">
                            {sidebarOpen ? "Close sidebar" : "Open sidebar"}
                        </span>
                    </Button>
                )}

                <ChatWindow
                    chatId={chatId}
                    onConversationCreated={handleConversationCreated}
                    sidebarOpen={sidebarOpen}
                    onToggleSidebar={isMobile ? toggleSidebar : undefined}
                />
            </div>

            {/* Right-side region: the preview pane and the artifacts list are
                mutually exclusive - only one renders at a time (see
                PLAN_PANE_UX.md item 2). Hidden on mobile to avoid crowding
                the chat window. */}
            {!isMobile && (
                artifactPane.isOpen ? (
                    <ArtifactPreviewPane
                        artifact={artifactPane.currentArtifact}
                        onClose={artifactPane.close}
                        width={artifactPane.width}
                        onWidthChange={artifactPane.setWidth}
                        artifacts={conversationArtifacts}
                        onSelectArtifact={artifactPane.open}
                    />
                ) : (
                    <ArtifactsPanel
                        artifacts={conversationArtifacts}
                        loading={artifactsLoading}
                        onOpenArtifact={artifactPane.open}
                    />
                )
            )}
        </section>
    );
}
