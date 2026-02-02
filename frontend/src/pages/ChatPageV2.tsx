import { useParams } from "react-router-dom";
import ChatListing from "@/components/chat/ChatListing";
import ChatWindow from "@/components/chat/ChatWindowV2";

export function ChatPage(){
    const { chatId: routeChatId } = useParams<{ chatId?: string }>();
    const chatId = routeChatId && routeChatId !== 'new' ? routeChatId : null;

    return (
        <section className="flex h-screen overflow-hidden">
            <ChatListing/>
            <ChatWindow chatId={chatId} />
        </section>
    )
}