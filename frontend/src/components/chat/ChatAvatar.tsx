import { cn } from "@/lib/utils";
import { cva, type VariantProps } from "class-variance-authority";
import { Avatar } from "../ui/avatar";
import { AvatarFallbackProps } from "@radix-ui/react-avatar";

const chatAvatarVariants=cva(
    "",
    {
        variants:{
            variant:{
                listing_ai:"h-6 w-6 text-[10px] rounded-lg flex items-center justify-center text-panel font-semibold shadow-inner",
                chat_ai:"h-8 w-8 text-xs rounded-lg flex items-center justify-center text-panel font-semibold shadow-inner",
                chat_user:"h-8 w-8 rounded-full bg-gradient-to-tr from-signal to-signal-ink border border-panel/10 flex items-center justify-center text-[10px] font-bold text-panel shadow-sm"
            },
        },
        defaultVariants:{
            variant:"chat_ai"
        }
    }
)

type ChatAvatarProps = AvatarFallbackProps & VariantProps<typeof chatAvatarVariants> & {
    color?: string | null;
};

export default function ChatAvatar({children,className,variant,color,...props}:ChatAvatarProps){
    // Apply color as inline style if provided, otherwise use default background classes
    const style = color && (variant === 'listing_ai' || variant === 'chat_ai') 
        ? { backgroundColor: color } 
        : undefined;
    
    // Use default background classes only if no color is provided
    const bgClass = !color && (variant === 'listing_ai' || variant === 'chat_ai')
        ? (variant === 'listing_ai' ? 'bg-transparent' : 'bg-transparent')
        : '';
    
    return (
        <Avatar 
            className={cn(chatAvatarVariants({variant,className:`static ${className}`}), bgClass)} 
            style={style}
            {...props}
        >
            {children}
        </Avatar>
    )
}