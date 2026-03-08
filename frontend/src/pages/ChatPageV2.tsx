import { useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import ChatListing from "@/components/chat/ChatListing";
import ChatWindow from "@/components/chat/ChatWindowV2";

export { ChatPage };
export default ChatPage;

function ChatPage(){
    const navigate = useNavigate();
    const { chatId: routeChatId } = useParams<{ chatId?: string }>();
    const chatId = routeChatId && routeChatId !== 'new' ? routeChatId : null;

    const [sidebarOpen, setSidebarOpen] = useState(true);
    const toggleSidebar = useCallback(() => setSidebarOpen((prev) => !prev), []);

    const handleConversationCreated = useCallback((conversationId: string, agentName?: string) => {
        // Dispatch custom event to notify ChatListing
        const event = new CustomEvent('huf:conversation-created', {
            detail: { conversationId, agentName }
        });
        window.dispatchEvent(event);
        
        // Navigate to the conversation
        navigate(`/chat/${conversationId}`);
    }, [navigate]);

    return (
        <section className="flex h-full overflow-hidden relative">
            {/* Collapsible sidebar */}
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

            {/* Chat window */}
            <div className="flex-1 min-h-0 h-full relative">
                {/* Sidebar toggle button */}
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
                    <span className="sr-only">{sidebarOpen ? 'Close sidebar' : 'Open sidebar'}</span>
                </Button>

                <ChatWindow chatId={chatId} onConversationCreated={handleConversationCreated} />
            </div>
        </section>
    )
}