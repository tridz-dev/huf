import React, { useState } from "react";
import { MemoryRecord } from "@/types/memory";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Archive, Brain, Calendar, Info, ShieldAlert, Sparkles, AlertTriangle, MessageSquare, ArchiveX } from "lucide-react";
import { toast } from "sonner";
import { memoryApi } from "@/services/memoryApi";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

interface MemoryCardProps {
  memory: MemoryRecord;
  onArchive: (id: string) => void;
}

const getRecordTypeColor = (type: string) => {
  switch (type.toLowerCase()) {
    case "fact": return "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200";
    case "preference": return "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200";
    case "instruction": return "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200";
    case "context": return "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200";
    case "reflection": return "bg-indigo-100 text-indigo-800 dark:bg-indigo-900 dark:text-indigo-200";
    default: return "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200";
  }
};

const getRecordTypeIcon = (type: string) => {
  switch (type.toLowerCase()) {
    case "fact": return <Info className="h-3 w-3 mr-1" />;
    case "preference": return <Sparkles className="h-3 w-3 mr-1" />;
    case "instruction": return <AlertTriangle className="h-3 w-3 mr-1" />;
    case "context": return <Brain className="h-3 w-3 mr-1" />;
    case "reflection": return <ShieldAlert className="h-3 w-3 mr-1" />;
    default: return <MessageSquare className="h-3 w-3 mr-1" />;
  }
};

export const MemoryCard: React.FC<MemoryCardProps> = ({ memory, onArchive }) => {
  const [isArchiving, setIsArchiving] = useState(false);

  const handleArchive = async () => {
    try {
      setIsArchiving(true);
      await memoryApi.archiveMemoryRecord(memory.name);
      toast.success("Memory Archived", {
        description: "The memory record has been successfully archived.",
      });
      onArchive(memory.name);
    } catch (error) {
      toast.error("Error", {
        description: "Failed to archive memory.",
      });
      setIsArchiving(false);
    }
  };

  const formattedDate = new Date(memory.modified).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric'
  });

  return (
    <Card className="flex flex-col h-full hover:shadow-md transition-all duration-200 border-border/50 bg-card/50">
      <CardHeader className="pb-3 flex-row justify-between items-start gap-4">
        <div className="space-y-1">
          <Badge variant="outline" className={`border-0 mb-1 ${getRecordTypeColor(memory.record_type)}`}>
            {getRecordTypeIcon(memory.record_type)}
            {memory.record_type}
          </Badge>
          <CardTitle className="text-base line-clamp-1">{memory.title}</CardTitle>
        </div>
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-muted-foreground hover:text-destructive -mt-1 -mr-1"
                onClick={handleArchive}
                disabled={isArchiving}
              >
                {isArchiving ? <ArchiveX className="h-4 w-4 animate-pulse" /> : <Archive className="h-4 w-4" />}
              </Button>
            </TooltipTrigger>
            <TooltipContent>Archive memory</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </CardHeader>
      <CardContent className="flex-grow">
        <p className="text-sm text-muted-foreground line-clamp-3 leading-relaxed">
          {memory.summary_text}
        </p>
      </CardContent>
      <CardFooter className="pt-3 border-t text-xs text-muted-foreground flex justify-between items-center bg-muted/20">
        <div className="flex items-center gap-1.5">
          <Calendar className="h-3 w-3" />
          <span>{formattedDate}</span>
        </div>
        <div className="flex items-center gap-3">
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger>
                <div className="flex items-center gap-1">
                  <span className="font-medium">Score:</span> {memory.importance_score}/10
                </div>
              </TooltipTrigger>
              <TooltipContent>Importance Score</TooltipContent>
            </Tooltip>
          </TooltipProvider>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger>
                <div className="flex items-center gap-1">
                  <span className="font-medium">Conf:</span> {(memory.confidence * 100).toFixed(0)}%
                </div>
              </TooltipTrigger>
              <TooltipContent>Confidence Level</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
      </CardFooter>
    </Card>
  );
};
