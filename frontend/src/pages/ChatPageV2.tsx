import ChatListing from "@/components/chat/ChatListing";
import ChatWindow from "@/components/chat/ChatWindowV2";

export function ChatPage(){
    return (
        <section className="flex">
            <ChatListing/>
            <ChatWindow/>
        </section>
    )
}