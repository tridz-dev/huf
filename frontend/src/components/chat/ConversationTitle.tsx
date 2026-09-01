import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";
import React, { useState, useRef, forwardRef, useImperativeHandle, useEffect } from "react";
import { toast } from 'sonner';
import { updateConversationTitle } from "@/services/chatApi";
import { useTypewriterText } from "@/hooks/useTypewriterText";

const conversationTitleVariants = cva(
    "px-1 w-full truncate text-ink bg-transparent outline-none focus-visible:ring-1 focus-visible:ring-primary rounded-sm cursor-pointer",
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

type ConversationTitleProps = {
    value: string,
    conversationId: string,
    animate?: boolean,
    className?: string,
} & VariantProps<typeof conversationTitleVariants>

const ConversationTitle = forwardRef<ConversationTitleRef, ConversationTitleProps>(
    function ConversationTitle({variant, value, conversationId, animate = false, className}, ref){
    const [active, setActive] = useState(false);
    const [shouldAnimate, setShouldAnimate] = useState(false);
    const inputRef = useRef<HTMLInputElement>(null);
    const isProgrammaticActivation = useRef(false);
    const blurTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const displayText = useTypewriterText(value, { enabled: shouldAnimate && !active });

    useEffect(() => {
        if (animate) {
            setShouldAnimate(true);
            return;
        }
        setShouldAnimate(false);
    }, [animate, value]);

    useEffect(() => {
        if (!active && inputRef.current && inputRef.current.value !== value) {
            inputRef.current.value = value;
        }
    }, [value, active]);

    function handleDisableReadOnlyFocus(e:React.MouseEvent<HTMLInputElement>){
        if (!active && !isProgrammaticActivation.current){
            e.preventDefault()
        }
    }

    function handleFocus(){
        if (blurTimeoutRef.current) {
            clearTimeout(blurTimeoutRef.current);
            blurTimeoutRef.current = null;
        }
        if (isProgrammaticActivation.current && inputRef.current) {
            inputRef.current.readOnly = false;
        }
    }
    
    function toggleInput(){
        setShouldAnimate(false);
        isProgrammaticActivation.current = false;
        setActive((prev)=>!prev)
        setTimeout(()=>inputRef?.current?.focus(),0)
    }

    function activateInput(){
        setShouldAnimate(false);
        if (blurTimeoutRef.current) {
            clearTimeout(blurTimeoutRef.current);
            blurTimeoutRef.current = null;
        }
        isProgrammaticActivation.current = true;
        setActive(true);
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                if (inputRef?.current) {
                    inputRef.current.readOnly = false;
                    setTimeout(() => {
                        if (inputRef?.current && isProgrammaticActivation.current) {
                            inputRef.current.focus();
                            inputRef.current.select();
                        }
                    }, 10);
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
        if (isProgrammaticActivation.current) {
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
        if (e.key == "Escape" && active){
            resetValue()
            inputRef.current?.blur()
            setActive(false)
        }
    }

    async function updateTitle(nextValue:string){
        try{
            await updateConversationTitle(conversationId, nextValue)
            toast.success("Conversation title updated")
        }catch(error){
            toast.error('Failed to update conversation title', {
                description: error instanceof Error ? error.message : 'An error occurred',
            });
            resetValue();
        }
    }

    if (!active) {
        return (
            <div
                className={cn(conversationTitleVariants({ variant }), "relative min-w-0", className)}
                onDoubleClick={toggleInput}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                    if (e.key === 'Enter') toggleInput();
                }}
            >
                <span className="invisible block truncate" aria-hidden="true">
                    {value}
                </span>
                <span className="absolute inset-0 truncate px-1">
                    {shouldAnimate ? displayText : value}
                </span>
            </div>
        );
    }

    return (
        <input
        ref={inputRef} 
        className={cn(conversationTitleVariants({variant}), className)}
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
