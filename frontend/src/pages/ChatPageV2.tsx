import { useEffect, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import ChatListing from "@/components/chat/ChatListing";
import ChatWindow from "@/components/chat/ChatWindowV2";
import { findScrollableContainer } from "@/utils/htmlUtils";

export function ChatPage(){
    const navigate = useNavigate();
    const { chatId: routeChatId } = useParams<{ chatId?: string }>();
    const chatId = routeChatId && routeChatId !== 'new' ? routeChatId : null;
    const chatWindowRef = useRef<HTMLDivElement>(null);

    const handleConversationCreated = (conversationId: string) => {
        navigate(`/chat/${conversationId}`);
    };

    // Scroll to bottom when chat content changes
    useEffect(() => {
        const scrollToBottom = () => {
            if (!chatWindowRef.current) 
                return;
            const container = findScrollableContainer(chatWindowRef.current);
            
            if (container === window) {
                window.scrollTo({
                    top: document.documentElement.scrollHeight,
                    behavior: 'smooth',
                });
            } else if (container instanceof HTMLElement) {
                container.scrollTo({
                    top: container.scrollHeight,
                    behavior: 'smooth',
                });
            }
        };
        scrollToBottom();
    }, [chatId]);

    return (
        <section className="flex h-screen overflow-hidden">
            <ChatListing/>
            <div className="flex-1 min-h-0" ref={chatWindowRef}>
                <ChatWindow chatId={chatId} onConversationCreated={handleConversationCreated} />
            </div>
        </section>
    )
}