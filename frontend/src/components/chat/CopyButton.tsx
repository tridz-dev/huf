import { useEffect, useState } from "react";
import { Button } from "../ui/button";
import { Check, Copy } from "lucide-react";
import { toast } from "sonner";

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
      if (!navigator?.clipboard) {
        throw new Error('Clipboard API not available');
      }
      await navigator.clipboard.writeText(content);
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
          size="icon"
          className="h-7 w-7"
          onClick={handleCopy}
          aria-label={copied ? 'Copied' : 'Copy response'}
        >
          {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
        </Button>
  )
}