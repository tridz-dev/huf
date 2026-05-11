import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { X } from "lucide-react";
import ChatListing from "@/components/chat/ChatListing";
import ChatWindow from "@/components/chat/ChatWindowV2";
import { Button } from "@/components/ui/button";
import { SidebarProvider } from "@/components/ui/sidebar";

export default function StandaloneChatPage() {
    const navigate = useNavigate();
    const { chatId: routeChatId } = useParams<{ chatId?: string }>();
    const chatId = routeChatId && routeChatId !== "new" ? routeChatId : null;
    const [drawerOpen, setDrawerOpen] = useState(false);

    useEffect(() => {
        setDrawerOpen(false);
    }, [chatId]);

    const handleConversationCreated = useCallback(
        (conversationId: string, agentName?: string) => {
            const event = new CustomEvent("huf:conversation-created", {
                detail: { conversationId, agentName },
            });
            window.dispatchEvent(event);
            navigate(`/ui/chat/${conversationId}`);
        },
        [navigate],
    );

    return (
        <SidebarProvider defaultOpen={false}>
            <section className="relative flex h-dvh w-full overflow-hidden bg-background pb-[env(safe-area-inset-bottom)]">
                {drawerOpen && (
                    <div className="absolute inset-0 z-40 bg-sidebar">
                        <ChatListing onClose={() => setDrawerOpen(false)} />
                    </div>
                )}
                <ChatWindow
                    chatId={chatId}
                    onConversationCreated={handleConversationCreated}
                    onToggleSidebar={() => setDrawerOpen(true)}
                    standalone
                />
                {drawerOpen && (
                    <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="fixed right-4 top-[calc(1rem+env(safe-area-inset-top))] z-50 h-9 w-9 bg-white/80 text-zinc-500 shadow-sm"
                        onClick={() => setDrawerOpen(false)}
                    >
                        <X className="h-4 w-4" />
                        <span className="sr-only">Close conversations</span>
                    </Button>
                )}
            </section>
        </SidebarProvider>
    );
}
