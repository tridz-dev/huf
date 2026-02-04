import { PencilIcon } from "lucide-react";
import { ContextMenu, ContextMenuContent, ContextMenuGroup, ContextMenuItem, ContextMenuTrigger } from "../ui/context-menu";

type ConversationMenuProps ={
    children:React.ReactNode
}
export default function ConversationMenu({children}:ConversationMenuProps){
    return (
        <ContextMenu>
            <ContextMenuTrigger>
                {children}
            </ContextMenuTrigger>
            <ContextMenuContent>
            <ContextMenuGroup>
                <ContextMenuItem>
                    <PencilIcon/>
                    Rename
                </ContextMenuItem>
            </ContextMenuGroup>
            </ContextMenuContent>
        </ContextMenu>
    )
}