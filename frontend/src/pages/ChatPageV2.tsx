import ChatListing from "@/components/chat/ChatListing";
import ChatWindow from "@/components/chat/ChatWindowV2";

export function ChatPage(){
    return (
        <section className="flex h-screen overflow-hidden">
            <ChatListing/>
            <ChatWindow/>
        </section>
    )
}