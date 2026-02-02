import { cn } from "@/lib/utils";
import { cva, type VariantProps } from "class-variance-authority";
import { Avatar } from "../ui/avatar";
import { AvatarFallbackProps } from "@radix-ui/react-avatar";

const chatAvatarVariants=cva(
    "",
    {
        variants:{
            variant:{
                listing_ai:"h-5 w-5 text-[10px] rounded-lg bg-blue-600 flex items-center justify-center text-white font-semibold shadow-inner",
                chat_ai:"h-8 w-8 text-xs rounded-lg bg-purple-600 flex items-center justify-center text-white font-semibold shadow-inner",
                chat_user:"h-8 w-8 rounded-full bg-gradient-to-tr from-orange-400 to-pink-600 border border-white/10 flex items-center justify-center text-[10px] font-bold text-white shadow-sm"
            },
        },
        defaultVariants:{
            variant:"chat_ai"
        }
    }
)

type ChatAvatarProps = AvatarFallbackProps & VariantProps<typeof chatAvatarVariants>;

export default function ChatAvatar({children,className,variant,...props}:ChatAvatarProps){
    return (
        <Avatar className={cn(chatAvatarVariants({variant,className}))} {...props}>
            {children}
        </Avatar>
    )
}