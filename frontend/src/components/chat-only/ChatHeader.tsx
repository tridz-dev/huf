import { ChevronsUpDown, LogOut, Zap } from "lucide-react";
import { useUser } from "@/contexts/UserContext";
import UserAvatar from "@/components/UserAvatar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

interface ChatHeaderProps {
  agentLabel?: string;
}

export function ChatHeader({ agentLabel }: ChatHeaderProps) {
  const { logout, user } = useUser();
  const displayName = user?.full_name || user?.name || "User";
  const displayEmail = user?.email || "";

  return (
    <header className="h-14 shrink-0 border-b border-zinc-200 bg-white/90 backdrop-blur supports-[backdrop-filter]:bg-white/75">
      <div className="mx-auto flex h-full w-full max-w-5xl items-center justify-between gap-3 px-3 sm:px-4">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Zap className="size-4" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="truncate text-sm font-semibold text-zinc-950">HufAI</span>
              {agentLabel && (
                <span className="hidden max-w-[180px] truncate rounded-full border border-zinc-200 px-2 py-0.5 text-xs text-zinc-600 sm:inline">
                  {agentLabel}
                </span>
              )}
            </div>
            <p className="truncate text-xs text-zinc-500">Chat</p>
          </div>
        </div>

        {user && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" className="h-10 min-w-10 gap-2 px-2">
                <UserAvatar className="size-8 rounded-full" />
                <span className="hidden max-w-32 truncate text-sm font-medium sm:inline">
                  {displayName}
                </span>
                <ChevronsUpDown className="hidden size-4 text-zinc-500 sm:block" />
                <span className="sr-only">Open user menu</span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-64">
              <DropdownMenuLabel className="font-normal">
                <div className="flex items-center gap-2">
                  <UserAvatar className="size-8 rounded-full" />
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{displayName}</p>
                    {displayEmail && (
                      <p className="truncate text-xs text-muted-foreground">{displayEmail}</p>
                    )}
                  </div>
                </div>
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={logout} className="text-red-500 focus:text-red-700">
                <LogOut className="mr-2 size-4" />
                Log out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>
    </header>
  );
}
