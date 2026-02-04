import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";
import React, { useState,useRef } from "react";

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
    return (
        <input
        ref={inputRef} 
        className={cn(conversationTitleVariants({variant}))}
        defaultValue={value}
        readOnly={!active}
        onDoubleClick={activateInput}
        onMouseDown={handleDisableReadOnlyFocus}
        />
    )
}