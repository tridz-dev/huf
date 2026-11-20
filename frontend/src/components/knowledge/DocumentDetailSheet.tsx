import { Download } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { formatTimeAgo } from '@/utils/time';
import type { KnowledgeInputDoc } from '@/types/knowledge.types';
import { itemReason, itemStatusLabel } from './import/ingestionLabels';
import { inputOrigin, inputTitle } from './DocumentsTable';

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-3 gap-2 border-b py-2 text-sm">
      <dt className="text-steel">{label}</dt>
      <dd className="col-span-2 break-words">{children}</dd>
    </div>
  );
}

interface DocumentDetailSheetProps {
  input: KnowledgeInputDoc | null;
  onOpenChange: (open: boolean) => void;
}

export function DocumentDetailSheet({ input, onOpenChange }: DocumentDetailSheetProps) {
  const reason = input ? itemReason(input) : '';
  return (
    <Sheet open={input !== null} onOpenChange={onOpenChange}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-md" data-testid="document-detail">
        {input && (
          <>
            <SheetHeader>
              <SheetTitle className="break-words pr-6">{inputTitle(input)}</SheetTitle>
              <SheetDescription>Document details</SheetDescription>
            </SheetHeader>
            <dl className="mt-4">
              <Row label="Origin">{inputOrigin(input).label}</Row>
              <Row label="Status">
                <Badge variant="pill-neutral">{itemStatusLabel(input.status)}</Badge>
              </Row>
              {reason && <Row label="Reason">{reason}</Row>}
              <Row label="Sections">{(input.chunks_created ?? 0).toLocaleString()}</Row>
              <Row label="Added">{formatTimeAgo(input.creation)}</Row>
              {input.input_type === 'File' && input.file && (
                <Row label="File">
                  <a
                    href={input.file}
                    target="_blank"
                    rel="noreferrer"
                    download
                    className="inline-flex items-center gap-1.5 text-signal-ink underline-offset-4 hover:underline"
                  >
                    <Download className="h-3.5 w-3.5" />
                    Download file
                  </a>
                </Row>
              )}
            </dl>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
