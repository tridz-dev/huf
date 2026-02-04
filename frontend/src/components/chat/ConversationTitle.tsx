import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";
import React, { useState,useRef } from "react";
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

type ConversationTitle = {
    value:string,
    conversationId:string
} & VariantProps<typeof conversationTitleVariants>

export default function ConversationTitle({variant,value,conversationId}:ConversationTitle){
    const [active,setActive]=useState(false);
    const inputRef=useRef<HTMLInputElement>(null);
    
    function handleDisableReadOnlyFocus(e:React.MouseEvent<HTMLInputElement>){
        if (!active){
            e.preventDefault()
        }
    }
    
    function activateInput(){
        setActive((prev)=>!prev)
        setTimeout(()=>inputRef?.current?.focus(),0)
    }

    function resetValue(){
        if (inputRef?.current)
            inputRef.current.value=value
    }

    function onBlur(e:React.FocusEvent<HTMLInputElement>){
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
        onDoubleClick={activateInput}
        onMouseDown={handleDisableReadOnlyFocus}
        onKeyDown={handleEnterKey}
        onBlur={onBlur}
        />
    )
}