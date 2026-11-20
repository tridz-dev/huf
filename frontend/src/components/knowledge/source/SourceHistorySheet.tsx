import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { KnowledgeActivityTab } from '../KnowledgeActivityTab';

interface SourceHistorySheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  knowledgeSource: string;
  refreshKey: number;
}

export function SourceHistorySheet({ open, onOpenChange, knowledgeSource, refreshKey }: SourceHistorySheetProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="flex w-full flex-col gap-0 p-0 sm:max-w-md">
        <SheetHeader className="border-b border-line px-6 py-4">
          <SheetTitle>History</SheetTitle>
          <SheetDescription className="sr-only">Recent activity on this source</SheetDescription>
        </SheetHeader>
        <div className="flex-1 overflow-y-auto px-6 py-5">
          <KnowledgeActivityTab knowledgeSource={knowledgeSource} refreshKey={refreshKey} />
        </div>
      </SheetContent>
    </Sheet>
  );
}
