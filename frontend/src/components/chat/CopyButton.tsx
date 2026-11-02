import { useEffect, useState } from "react";
import { Button } from "../ui/button";
import { Check, Copy } from "lucide-react";
import { toast } from "sonner";
import { copyText } from '@/lib/clipboard';

export function CopyButton({ content}: { content: string}) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) {
      return;
    }
    const timer = setTimeout(() => setCopied(false), 4000);
    return () => clearTimeout(timer);
  }, [copied]);

  const handleCopy = async () => {
    if (!content) {
      return;
    }

    try {
      if (!(await copyText(content))) throw new Error('Copy failed');
      setCopied(true);
      toast.success('Response copied');
    } catch (error) {
      console.error(error);
      toast.error('Unable to copy response');
    }
  };
  return (
    <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          className="text-steel-soft hover:text-ink"
          onClick={handleCopy}
          aria-label={copied ? 'Copied' : 'Copy response'}
        >
          {copied ? <Check className="size-[15px]" /> : <Copy className="size-[15px]" />}
        </Button>
  )
}