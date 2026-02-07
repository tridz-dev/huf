import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";
import React, { useState, useRef, forwardRef, useImperativeHandle } from "react";
import { toast } from 'sonner';
import { updateConversationTitle } from "@/services/chatApi";

const conversationTitleVariants = cva(
    "px-1 w-full font-medium truncate text-zinc-900 bg-transparent outline-none focus-visible:ring-1 focus-visible:ring-primary rounded-sm cursor-pointer",
    {
        variants:{
            variant:{
                agent_list:"text-xs",
                recents_list:"text-sm block"
            }
        }
    }
)

export interface ConversationTitleRef {
    activateInput: () => void;
}

type ConversationTitle = {
    value:string,
    conversationId:string
} & VariantProps<typeof conversationTitleVariants>

const ConversationTitle = forwardRef<ConversationTitleRef, ConversationTitle>(
    function ConversationTitle({variant,value,conversationId}, ref){
    const [active,setActive]=useState(false);
    const inputRef=useRef<HTMLInputElement>(null);
    const isProgrammaticActivation = useRef(false);
    const blurTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    
    function handleDisableReadOnlyFocus(e:React.MouseEvent<HTMLInputElement>){
        // Only prevent default if not active AND not programmatically activating
        // This prevents interference with programmatic focus
        if (!active && !isProgrammaticActivation.current){
            e.preventDefault()
        }
    }

    function handleFocus(){
        // Clear any pending blur timeout
        if (blurTimeoutRef.current) {
            clearTimeout(blurTimeoutRef.current);
            blurTimeoutRef.current = null;
        }
        // If we're programmatically activating, ensure the input is not readOnly
        // This prevents the browser from blurring due to readOnly state changes
        if (isProgrammaticActivation.current && inputRef.current) {
            inputRef.current.readOnly = false;
        }
    }
    
    // Internal function for double-click toggle behavior
    function toggleInput(){
        isProgrammaticActivation.current = false;
        setActive((prev)=>!prev)
        setTimeout(()=>inputRef?.current?.focus(),0)
    }

    // Exposed function for programmatic activation (always activates, doesn't toggle)
    function activateInput(){
        // Clear any pending blur
        if (blurTimeoutRef.current) {
            clearTimeout(blurTimeoutRef.current);
            blurTimeoutRef.current = null;
        }
        // Set flag IMMEDIATELY to prevent onMouseDown from interfering
        isProgrammaticActivation.current = true;
        // Always activate (don't toggle) - ensures input is ready for editing when called from context menu
        setActive(true);
        // Use requestAnimationFrame to ensure DOM is updated before focusing
        // This is especially important when called from context menu which may be closing
        requestAnimationFrame(() => {
            // Double RAF to ensure menu has fully closed and DOM is stable
            requestAnimationFrame(() => {
                if (inputRef?.current) {
                    // Explicitly set readOnly to false before focusing to prevent blur
                    inputRef.current.readOnly = false;
                    // Small delay to ensure readOnly change is processed
                    setTimeout(() => {
                        if (inputRef?.current && isProgrammaticActivation.current) {
                            inputRef.current.focus();
                            // Select all text for better UX when renaming
                            inputRef.current.select();
                        }
                    }, 10);
                    // Reset flag after focus has stabilized
                    setTimeout(() => {
                        isProgrammaticActivation.current = false;
                    }, 100);
                }
            });
        });
    }

    useImperativeHandle(ref, () => ({
        activateInput
    }));

    function resetValue(){
        if (inputRef?.current)
            inputRef.current.value=value
    }

    function onBlur(e:React.FocusEvent<HTMLInputElement>){
        // Don't process blur if we're programmatically activating (prevents race condition)
        if (isProgrammaticActivation.current) {
            // If we're programmatically activating and blur happens, refocus after a short delay
            blurTimeoutRef.current = setTimeout(() => {
                if (isProgrammaticActivation.current && inputRef.current) {
                    inputRef.current.focus();
                }
            }, 10);
            return;
        }
        setActive(false)
        if(!e.target.value){
            toast.error("Title cannot be empty!")
            resetValue()
            return
        }
        if (e.target.value === value)
            return
        updateTitle(e.target.value)
        if (inputRef.current){
            inputRef.current.scrollTo({
                left:0
            })
        }
    }

    function handleEnterKey(e:React.KeyboardEvent<HTMLInputElement>){
        if (e.key == "Enter" && active && inputRef?.current && (inputRef?.current.value != value)){
            inputRef.current.blur()
        }
    }

    async function updateTitle(value:string){
        try{
            await updateConversationTitle(conversationId,value)
            toast.success("Conversation title updated")
        }catch(error){
            toast.error('Failed to update conversation title', {
                description: error instanceof Error ? error.message : 'An error occurred',
            });
            resetValue();
        }
    }

    return (
        <input
        ref={inputRef} 
        className={cn(conversationTitleVariants({variant}))}
        defaultValue={value}
        readOnly={!active}
        onDoubleClick={toggleInput}
        onMouseDown={handleDisableReadOnlyFocus}
        onFocus={handleFocus}
        onKeyDown={handleEnterKey}
        onBlur={onBlur}
        />
    )
});

export default ConversationTitle;