import { useEffect } from "react";
import { useSidebar } from "../ui/sidebar";
import { ChatWindowHeader } from "./ChatWindowHeader";
import { ChatMessageList } from "./ChatMessageList";

interface ChatWindowProps {
    chatId?: string | null;
    onConversationCreated?: (conversationId: string, agentName?: string) => void;
    sidebarOpen?: boolean;
    onToggleSidebar?: () => void;
}

export default function ChatWindow({
    chatId: chatIdProp,
    onConversationCreated,
    sidebarOpen,
    onToggleSidebar,
}: ChatWindowProps) {
    const { setOpen } = useSidebar();

    // Close app sidebar once on mount so chat gets full width
    useEffect(() => {
        setOpen(false);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    return (
        <div className="w-full h-full flex flex-col overflow-hidden bg-background">
            <ChatWindowHeader
                chatId={chatIdProp}
                sidebarOpen={sidebarOpen}
                onToggleSidebar={onToggleSidebar}
            />
            <ChatMessageList chatId={chatIdProp} onConversationCreated={onConversationCreated} />
        </div>
    );
}
