import { useState } from "react";
import { PencilIcon, GitBranchIcon, PinIcon, PinOffIcon, FolderInputIcon, FolderMinusIcon } from "lucide-react";
import { ContextMenu, ContextMenuContent, ContextMenuGroup, ContextMenuItem, ContextMenuTrigger } from "../ui/context-menu";
import { pinConversation, unpinConversation, setConversationProject } from "@/services/projectApi";
import { handleFrappeError } from "@/lib/frappe-error";
import { MoveToProjectDialog } from "./projects/MoveToProjectDialog";

type ConversationMenuProps ={
    children:React.ReactNode
    conversationId?: string
    isPinned?: boolean
    /** HUF Project this conversation currently belongs to, if any. Drives
     * the spec §13 label switch ("Move to Project…" vs "Move to another
     * Project…") and whether "Remove from Project" is shown at all. */
    currentProject?: string | null
    onRename?: () => void
    onFork?: () => void
    onPinChange?: (conversationId: string, isPinned: boolean) => void
    /** Fired after the conversation's project changes (move or remove), so
     * the caller can refresh whatever list/view is currently showing it. */
    onProjectChange?: (conversationId: string, project: string | null) => void
}
export default function ConversationMenu({children, conversationId, isPinned, currentProject, onRename, onFork, onPinChange, onProjectChange}:ConversationMenuProps){
    const [moveDialogOpen, setMoveDialogOpen] = useState(false);

    function handleRename(e: Event){
        // Don't prevent default - let the menu close naturally
        // Only stop propagation to prevent Link navigation
        e.stopPropagation();
        // Use onSelect instead of onClick - Radix UI handles focus management better with onSelect
        // The menu will close automatically, and we'll focus the input after it closes
        // Call onRename after menu closes (Radix closes menu synchronously on onSelect)
        onRename?.();
    }

    function handleFork(e: Event){
        e.stopPropagation();
        onFork?.();
    }

    async function handleTogglePin(e: Event){
        e.stopPropagation();
        if (!conversationId) return;
        try {
            if (isPinned) {
                await unpinConversation(conversationId);
                onPinChange?.(conversationId, false);
            } else {
                await pinConversation(conversationId);
                onPinChange?.(conversationId, true);
            }
        } catch (error) {
            handleFrappeError(error, isPinned ? 'Error unpinning conversation' : 'Error pinning conversation');
        }
    }

    function handleOpenMoveDialog(e: Event){
        e.stopPropagation();
        setMoveDialogOpen(true);
    }

    async function handleMoveToProject(project: string){
        if (!conversationId) return;
        try {
            await setConversationProject(conversationId, project);
            onProjectChange?.(conversationId, project);
        } catch (error) {
            handleFrappeError(error, 'Error moving conversation to project');
        }
    }

    async function handleRemoveFromProject(e: Event){
        e.stopPropagation();
        if (!conversationId) return;
        try {
            await setConversationProject(conversationId, null);
            onProjectChange?.(conversationId, null);
        } catch (error) {
            handleFrappeError(error, 'Error removing conversation from project');
        }
    }

    return (
        <>
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
                <ContextMenuItem onSelect={handleFork}>
                    <GitBranchIcon className="w-4 h-4 mr-2"/>
                    Fork
                </ContextMenuItem>
                <ContextMenuItem onSelect={handleRename}>
                    <PencilIcon className="w-4 h-4 mr-2"/>
                    Rename
                </ContextMenuItem>
                {conversationId && (
                    <ContextMenuItem onSelect={handleTogglePin}>
                        {isPinned ? (
                            <PinOffIcon className="w-4 h-4 mr-2"/>
                        ) : (
                            <PinIcon className="w-4 h-4 mr-2"/>
                        )}
                        {isPinned ? 'Unpin' : 'Pin'}
                    </ContextMenuItem>
                )}
                {conversationId && (
                    <ContextMenuItem onSelect={handleOpenMoveDialog}>
                        <FolderInputIcon className="w-4 h-4 mr-2"/>
                        {currentProject ? 'Move to another Project…' : 'Move to Project…'}
                    </ContextMenuItem>
                )}
                {conversationId && currentProject && (
                    <ContextMenuItem onSelect={handleRemoveFromProject}>
                        <FolderMinusIcon className="w-4 h-4 mr-2"/>
                        Remove from Project
                    </ContextMenuItem>
                )}
            </ContextMenuGroup>
            </ContextMenuContent>
        </ContextMenu>
        {conversationId && (
            <MoveToProjectDialog
                open={moveDialogOpen}
                onOpenChange={setMoveDialogOpen}
                currentProject={currentProject}
                onMove={handleMoveToProject}
            />
        )}
        </>
    )
}
