import React, { useEffect, useState } from "react";
import { MemoryRecord } from "@/types/memory";
import { memoryApi } from "@/services/memoryApi";
import { MemoryCard } from "./MemoryCard";
import { Brain, MessageSquare, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useNavigate } from "react-router-dom";

export const MemoryList: React.FC = () => {
  const [memories, setMemories] = useState<MemoryRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const fetchMemories = async () => {
      try {
        setIsLoading(true);
        // Fetch User scope memories
        const records = await memoryApi.getMemoryRecords(undefined, "User");
        setMemories(records);
      } catch (err: any) {
        setError(err.message || "Failed to load memory records");
      } finally {
        setIsLoading(false);
      }
    };

    fetchMemories();
  }, []);

  const handleArchive = (archivedId: string) => {
    setMemories(memories.filter((m) => m.name !== archivedId));
  };

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] text-muted-foreground">
        <Loader2 className="h-8 w-8 animate-spin mb-4" />
        <p>Loading memories...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] text-destructive">
        <p>{error}</p>
        <Button variant="outline" className="mt-4" onClick={() => window.location.reload()}>
          Try Again
        </Button>
      </div>
    );
  }

  if (memories.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[500px] text-center px-4">
        <div className="h-16 w-16 bg-muted rounded-full flex items-center justify-center mb-6">
          <Brain className="h-8 w-8 text-muted-foreground" />
        </div>
        <h3 className="text-xl font-semibold mb-2">No memories yet</h3>
        <p className="text-muted-foreground max-w-sm mb-8">
          Your AI agents haven't learned anything about you yet. Start a conversation with a memory-enabled agent, and facts, preferences, and context will appear here automatically.
        </p>
        <Button onClick={() => navigate("/chat")} className="gap-2">
          Start a Chat
          <MessageSquare className="h-4 w-4" />
        </Button>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 pb-8">
      {memories.map((memory) => (
        <MemoryCard key={memory.name} memory={memory} onArchive={handleArchive} />
      ))}
    </div>
  );
};
