import { PencilIcon } from "lucide-react";
import { ContextMenu, ContextMenuContent, ContextMenuGroup, ContextMenuItem, ContextMenuTrigger } from "../ui/context-menu";

type ConversationMenuProps ={
    children:React.ReactNode
    onRename?: () => void
}
export default function ConversationMenu({children, onRename}:ConversationMenuProps){
    function handleRename(e: Event){
        // Don't prevent default - let the menu close naturally
        // Only stop propagation to prevent Link navigation
        e.stopPropagation();
        // Use onSelect instead of onClick - Radix UI handles focus management better with onSelect
        // The menu will close automatically, and we'll focus the input after it closes
        // Call onRename after menu closes (Radix closes menu synchronously on onSelect)
        onRename?.();
    }

    return (
        <ContextMenu>
            <ContextMenuTrigger>
                {children}
            </ContextMenuTrigger>
            <ContextMenuContent onCloseAutoFocus={(e) => {
                // Prevent focus from returning to trigger after menu closes
                // This prevents navigation and allows our programmatic focus to work
                e.preventDefault();
            }}>
            <ContextMenuGroup>
                <ContextMenuItem onSelect={handleRename}>
                    <PencilIcon className="w-4 h-4 mr-2"/>
                    Rename
                </ContextMenuItem>
            </ContextMenuGroup>
            </ContextMenuContent>
        </ContextMenu>
    )
}