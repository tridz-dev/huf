import { PageLayout } from "@/components/dashboard";
import { ExperimentalBadge } from "@/components/common/ExperimentalBadge";
import { MemoryList } from "@/components/memory/MemoryList";

export default function MemoryPage() {
  return (
    <PageLayout
      title="Memory"
      badge={<ExperimentalBadge />}
      subtitle="Facts, preferences, and context your AI agents have learned from conversations."
    >
      <MemoryList />
    </PageLayout>
  );
}
