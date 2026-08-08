import { useEffect, useState } from "react";
import { PageFrame } from "@/layouts/PageFrame";
import { ExperimentalBadge } from "@/components/common/ExperimentalBadge";
import { MemoryList } from "@/components/memory/MemoryList";
import { MemoryPolicyList } from "@/components/memory/MemoryPolicyList";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const VALID_TABS = ["memories", "policies"] as const;
type MemoryPageTab = (typeof VALID_TABS)[number];

function tabFromHash(): MemoryPageTab {
  const hash = window.location.hash.slice(1);
  return (VALID_TABS as readonly string[]).includes(hash) ? (hash as MemoryPageTab) : "memories";
}

export default function MemoryPage() {
  const [activeTab, setActiveTab] = useState<MemoryPageTab>(tabFromHash);

  useEffect(() => {
    const handleHashChange = () => setActiveTab(tabFromHash());
    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  const handleTabChange = (value: string) => {
    const tab = value as MemoryPageTab;
    setActiveTab(tab);
    if (tab === "memories") {
      window.history.replaceState(null, "", window.location.pathname);
    } else {
      window.location.hash = tab;
    }
  };

  return (
    <PageFrame
      title="Intelligence"
      badge={<ExperimentalBadge />}
      subtitle="Facts, preferences, and context your AI agents have learned from conversations."
    >
      <Tabs value={activeTab} onValueChange={handleTabChange} className="space-y-4">
        <TabsList>
          <TabsTrigger value="memories">Memories</TabsTrigger>
          <TabsTrigger value="policies">Policies</TabsTrigger>
        </TabsList>

        <TabsContent value="memories">
          <MemoryList />
        </TabsContent>

        <TabsContent value="policies">
          <MemoryPolicyList />
        </TabsContent>
      </Tabs>
    </PageFrame>
  );
}
