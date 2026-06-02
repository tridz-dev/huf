import React, { useState } from "react";
import { Brain, Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { MemoryRecord } from "@/types/memory";
import { call } from "@/lib/frappe-sdk";

interface MemoryContextBadgeProps {
  memoryRecordNames: string[];
}

export const MemoryContextBadge: React.FC<MemoryContextBadgeProps> = ({ memoryRecordNames }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [memories, setMemories] = useState<MemoryRecord[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const fetchMemories = async () => {
    if (memories.length > 0) return; // Already fetched
    try {
      setIsLoading(true);
      const fetched: MemoryRecord[] = [];
      for (const name of memoryRecordNames) {
        const result: any = await call.get("huf.ai.memory_tools.get_memory_record", { memory_record: name });
        if (result && result.message) fetched.push(result.message as MemoryRecord);
        else if (result) fetched.push(result as MemoryRecord);
      }
      setMemories(fetched);
    } catch (error) {
      console.error("Failed to fetch memories", error);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Popover open={isOpen} onOpenChange={(open) => {
      setIsOpen(open);
      if (open) fetchMemories();
    }}>
      <PopoverTrigger asChild>
        <Badge variant="secondary" className="cursor-pointer gap-1 font-normal text-xs bg-muted/50 hover:bg-muted text-muted-foreground border-0">
          <Brain className="h-3 w-3" />
          {memoryRecordNames.length} {memoryRecordNames.length === 1 ? 'memory' : 'memories'}
        </Badge>
      </PopoverTrigger>
      <PopoverContent className="w-80 p-0" align="start">
        <div className="bg-muted/30 p-3 border-b border-border/50">
          <h4 className="text-sm font-semibold flex items-center gap-2">
            <Brain className="h-4 w-4 text-primary" />
            Context Injected
          </h4>
          <p className="text-xs text-muted-foreground mt-1">
            The agent used these personal memories to personalize its response.
          </p>
        </div>
        <div className="p-2 max-h-[300px] overflow-y-auto">
          {isLoading ? (
            <div className="flex items-center justify-center py-4 text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
            </div>
          ) : memories.length === 0 ? (
            <div className="text-xs text-center py-4 text-muted-foreground">
              No memory details available.
            </div>
          ) : (
            <div className="space-y-2">
              {memories.map((m, idx) => (
                <div key={idx} className="bg-card p-2 rounded border text-xs">
                  <div className="font-medium mb-1">{m.title}</div>
                  <div className="text-muted-foreground line-clamp-2">{m.summary_text}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
};
