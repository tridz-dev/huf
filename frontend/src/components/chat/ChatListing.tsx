import { Clock4, Users } from "lucide-react"
import { Tabs, TabsList, TabsTrigger } from "../ui/tabs"

export default function ChatListing(){
    return (
        <div>
            <ChatListHeader/>
        </div>
    )
}

function ChatListHeader(){
    return(
        <div className="p-4 space-y-4 h-full min-h-screen md:max-w-xs bg-sidebar">
            <div>
                <h1 className="font-semibold text-lg tracking-tight">Workspaces</h1>
            </div>
            <Tabs defaultValue="agent">
                <TabsList className="w-full">
                    {LIST_TABS.map((tab)=>(
                        <TabsTrigger className="w-1/2 space-x-2 text-xs font-medium" value={tab.value}>
                            <tab.icon className="w-3 h-3"/>
                            <span>{tab.label}</span>
                        </TabsTrigger>
                    ))}
                </TabsList>
            </Tabs>
        </div>
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