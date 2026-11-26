import { Download, ExternalLink } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { formatTimeAgo } from '@/utils/time';
import type { KnowledgeInputDoc } from '@/types/knowledge.types';
import { itemReason, itemStatusLabel } from './import/ingestionLabels';
import { inputOrigin, inputTitle } from './inputDisplay';
import { IndexedText } from './source/IndexedText';

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-3 gap-2 border-b py-2 text-sm">
      <dt className="text-steel">{label}</dt>
      <dd className="col-span-2 break-words">{children}</dd>
    </div>
  );
}

const LINK_CLASS = 'inline-flex items-center gap-1.5 text-signal-ink underline-offset-4 hover:underline';

/** The original content: the uploaded file, the web page, or the typed text as a download. */
function OriginalLink({ input }: { input: KnowledgeInputDoc }) {
  if (input.input_type === 'File' && input.file) {
    return (
      <a href={input.file} target="_blank" rel="noreferrer" download className={LINK_CLASS}>
        <Download className="h-3.5 w-3.5" />
        Download original
      </a>
    );
  }
  if (input.input_type === 'URL' && input.url && /^https?:\/\//i.test(input.url)) {
    return (
      <a href={input.url} target="_blank" rel="noreferrer" className={LINK_CLASS}>
        <ExternalLink className="h-3.5 w-3.5" />
        Open page
      </a>
    );
  }
  if (input.input_type === 'Text' && input.text) {
    const href = `data:text/plain;charset=utf-8,${encodeURIComponent(input.text)}`;
    return (
      <a href={href} download={`${input.name}.txt`} className={LINK_CLASS}>
        <Download className="h-3.5 w-3.5" />
        Download original
      </a>
    );
  }
  return <span className="text-steel">Not available</span>;
}

interface DocumentDetailSheetProps {
  input: KnowledgeInputDoc | null;
  onOpenChange: (open: boolean) => void;
}

export function DocumentDetailSheet({ input, onOpenChange }: DocumentDetailSheetProps) {
  const reason = input ? itemReason(input) : '';
  return (
    <Sheet open={input !== null} onOpenChange={onOpenChange}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-lg" data-testid="document-detail">
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
              <Row label="Original">
                <OriginalLink input={input} />
              </Row>
            </dl>
            <IndexedText
              knowledgeInput={input.name}
              version={`${input.status}:${input.processed_at ?? ''}:${input.chunks_created ?? 0}`}
              indexed={input.status === 'Indexed'}
            />
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
