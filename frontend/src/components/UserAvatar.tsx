import {
    Avatar,
    AvatarFallback,
    AvatarImage,
  } from "@/components/ui/avatar";
import { useUser } from "@/contexts/UserContext";
import { cn } from "@/lib/utils";

export default function UserAvatar({className}: {className?: string}) {
    const { user } = useUser();
    if (!user) {
        return null;
    }
    const displayName = user.full_name || user.name;
    const initials = displayName.slice(0, 2).toUpperCase();
    return (
        <Avatar className={cn("h-8 w-8 rounded-lg", className)}>
            {user.user_image && (
                <AvatarImage src={user.user_image} alt={displayName} />
            )}
            <AvatarFallback className="rounded-lg bg-primary text-primary-foreground">
                {initials}
            </AvatarFallback>
        </Avatar>
    );
}