import { useEffect } from "react";
import { useSidebar } from "../ui/sidebar";
import { ChatWindowHeader } from "./ChatWindowHeader";
import { ChatMessageList } from "./ChatMessageList";

interface ChatWindowProps {
    chatId?: string | null;
    onConversationCreated?: (conversationId: string, agentName?: string) => void;
}

export default function ChatWindow({ chatId: chatIdProp, onConversationCreated }: ChatWindowProps){
    const {setOpen} = useSidebar();
    
    // Close sidebar on initial mount only
    useEffect(() => {
        setOpen(false);
    }, []);
    
    return (
        <div className="w-full h-full flex flex-col overflow-hidden bg-background">
           <ChatWindowHeader chatId={chatIdProp} />
           <ChatMessageList chatId={chatIdProp} onConversationCreated={onConversationCreated} />
        </div>
    )
}
