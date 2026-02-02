import { Clock4, Users } from "lucide-react"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../ui/tabs"
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "../ui/accordion"
import ChatAvatar from "./ChatAvatar"
import { Link } from "react-router-dom"

export default function ChatListing(){
    return (
        <div className="h-full min-h-screen min-w-96 bg-sidebar p-4 space-y-4">
            <ChatListHeader/>
            <Tabs defaultValue="agent" className="space-y-4">
                <TabsList className="w-full">
                    {LIST_TABS.map((tab)=>(
                        <TabsTrigger className="w-1/2 space-x-2 text-xs font-medium" value={tab.value}>
                            <tab.icon className="w-3 h-3"/>
                            <span>{tab.label}</span>
                        </TabsTrigger>
                    ))}
                </TabsList>
                <ChatListingAgent/>
                <ChatListingRecent/>
            </Tabs>
        </div>
    )
}

function ChatListHeader(){
    return(
        <div className="">
            <div>
                <h1 className="font-semibold text-lg tracking-tight">Workspaces</h1>
            </div>
        </div>
    )
}

function ChatListingAgent(){
    return (
        <TabsContent value="agent" >
            <Accordion type="multiple" className="space-y-4">
                <AccordionItem value="item-1" className="border-b-0">
                    <AccordionTrigger className="group gap-2 mb-1 py-1 px-1 hover:bg-zinc-200 cursor-pointer select-none rounded-lg" arrowPosition="left">
                        <div className="flex-1 flex gap-x-2 items-center">
                            <ChatAvatar variant="listing_ai">DE</ChatAvatar>
                            <span className="text-sm font-medium truncate text-zinc-500 group-hover:text-zinc-900 transition-colors">Agent Name Here</span>
                        </div>
                        <span className="text-[10px] text-zinc-400 bg-zinc-200 px-1.5 py-0.5 rounded-full border border-zinc-200 ml-auto">2</span>
                    </AccordionTrigger>
                    <AccordionContent className="space-y-0.5 ml-3 pl-3 border-l border-zinc-200 overflow-hidden transition-all duration-300 opacity-100">
                        <Link to="/chat" className="group flex flex-col p-2 rounded-md cursor-pointer transition-all border-l-2 bg-zinc-200 border-indigo-500">
                            <span className="text-xs font-medium truncate text-zinc-900">
                                Conversation Header Here
                            </span>
                            <p className="text-[10px] text-zinc-400 truncate mt-0.5 group-hover:text-zinc-500">Agent Name Here</p>
                        </Link>
                    </AccordionContent>
                </AccordionItem>
            </Accordion>
        </TabsContent>
    )
}

function ChatListingRecent(){
    return (
        <TabsContent value="recents">
            <span className="px-2 text-xs font-medium text-zinc-400 uppercase tracking-wider">THIS WEEK</span>
            {/* Chat Listing Here */}
            <div className="mt-2 space-y-1">
                {/* Active conversation */}
                <div className="flex p-3 gap-2 items-center rounded-lg cursor-pointer transition-all border bg-zinc-200 border-zinc-200">
                    <div className="flex flex-1 gap-2 items-center">
                        <ChatAvatar variant="chat_ai">DE</ChatAvatar>
                        <div className="mb-1">
                            <span className="text-sm font-medium truncate text-zinc-900">Conversation Header here</span>
                            <p className="text-xs truncate text-zinc-500">Agent Name heere</p>
                        </div>
                    </div>
                    <span className="mt-1.5 text-[10px] text-zinc-400 flex-shrink-0 justify-self-end self-start">2m ago</span>
                </div>
                <div className="flex p-3 gap-2 items-center rounded-lg cursor-pointer transition-all border border-transparent bg-transparent hover:bg-zinc-200">
                    <div className="flex flex-1 gap-2 items-center">
                        <ChatAvatar variant="chat_ai">DE</ChatAvatar>
                        <div className="mb-1">
                            <span className="text-sm font-medium truncate text-zinc-900">Conversation Header here</span>
                            <p className="text-xs truncate text-zinc-500">Agent Name heere</p>
                        </div>
                    </div>
                    <span className="mt-1.5 text-[10px] text-zinc-400 flex-shrink-0 justify-self-end self-start">2m ago</span>
                </div>
            </div>
        </TabsContent>
    )
}

const LIST_TABS = [
    {
        "value":"agent",
        "label":"By Agent",
        "icon":Users
    },
    {
        "value":"recents",
        "label":"Recents",
        "icon":Clock4
    }
]