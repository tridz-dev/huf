import { useEffect } from "react";
import { useSidebar } from "../ui/sidebar";
import ChatAvatar from "./ChatAvatar";
export default function ChatWindow(){
    const {setOpen} = useSidebar();
    
    // Close sidebar on initial mount only
    useEffect(() => {
        setOpen(false);
    }, []);
    
    return (
        <div className="w-full">
           <ChatWindowHeader/>
        </div>
    )
}

function ChatWindowHeader(){
    return (
        <header className="h-16 px-6 border-b border-zinc-200 flex items-center justify-between bg-white/80 backdrop-blur-md sticky top-0 z-10">
            <div className="flex gap-x-4 items-center">
                <ChatAvatar variant="chat_ai">
                    hi
                </ChatAvatar>
                <div className="flex flex-col">
                    <div className="flex gap-x-2 items-center">
                        <span className="font-semibold text-sm text-zinc-900">Content Strageist</span>
                        <span className="px-1.5 py-0.5 rounded bg-indigo-500/10 border border-indigo-500/20 text-[10px] font-medium text-indigo-400">
                            Clause Opus 4.0
                        </span>
                    </div>
                    <span className="text-xs text-zinc-500 max-w-[200px] truncate">test ets ttestsasjdlfkajspdhf ahsdfhajslkd fjaskhdjfla sdfkashjlk</span>
                </div>
            </div>
        </header>
    )
}