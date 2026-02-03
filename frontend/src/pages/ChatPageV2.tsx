import { useParams, useNavigate } from "react-router-dom";
import ChatListing from "@/components/chat/ChatListing";
import ChatWindow from "@/components/chat/ChatWindowV2";

export function ChatPage(){
    const navigate = useNavigate();
    const { chatId: routeChatId } = useParams<{ chatId?: string }>();
    const chatId = routeChatId && routeChatId !== 'new' ? routeChatId : null;

    const handleConversationCreated = (conversationId: string) => {
        navigate(`/chat/${conversationId}`);
    };

    return (
        <section className="flex h-full overflow-hidden">
            <ChatListing/>
            <div className="flex-1 min-h-0 h-full">
                <ChatWindow chatId={chatId} onConversationCreated={handleConversationCreated} />
            </div>
        </section>
    )
}