import { useState } from 'react';
import { Check, Copy, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { copyText } from '@/lib/clipboard';

/** Opens WhatsApp Manager's template page; the account ID is shown because the link cannot jump to it directly. */
export function ManagerLink({ url, businessId, showId = true }: { url?: string; businessId?: string; showId?: boolean }) {
  const [copied, setCopied] = useState(false);
  if (!url) return null;

  const copy = async () => {
    if (!(await copyText(businessId ?? ''))) return;
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="flex items-center gap-2">
      <Button variant="ghost" size="sm" asChild>
        <a href={url} target="_blank" rel="noopener noreferrer">
          <ExternalLink className="mr-1.5 h-4 w-4" /> Open in WhatsApp Manager
        </a>
      </Button>
      {showId && businessId && (
        <details className="text-[11px] text-steel">
          <summary className="cursor-pointer">Details</summary>
          <span className="mt-1 flex items-center gap-1">
            Account ID <span className="font-mono text-ink">{businessId}</span>
            <Button variant="ghost" size="icon" className="h-6 w-6" aria-label="Copy account ID" onClick={copy}>
              {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
            </Button>
          </span>
        </details>
      )}
    </div>
  );
}
