import { MemoryList } from "@/components/memory/MemoryList";

export default function MemoryPage() {
  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">Memory</h1>
        <p className="text-muted-foreground mt-2">
          Facts, preferences, and context your AI agents have learned from conversations.
        </p>
      </div>
      <MemoryList />
    </div>
  );
}
