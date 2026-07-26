import { useState } from 'react';
import { CodeBlock } from '../ai-elements/code-block';
import { Button } from './button';
import { Copy, Check } from 'lucide-react';
import { cn } from '@/lib/utils';

interface JsonViewerProps {
  value: string | object;
  className?: string;
  showCopyButton?: boolean;
}

/**
 * Reusable JSON viewer component with beautification and copy functionality
 */
export function JsonViewer({ value, className, showCopyButton = true }: JsonViewerProps) {
  const [copied, setCopied] = useState(false);

  // Parse and beautify JSON
  let jsonString = '';
  try {
    if (typeof value === 'string') {
      // Try to parse if it's a string
      const parsed = JSON.parse(value);
      jsonString = JSON.stringify(parsed, null, 2);
    } else {
      jsonString = JSON.stringify(value, null, 2);
    }
  } catch {
    // If parsing fails, use as-is
    jsonString = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  }

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(jsonString);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (error) {
      console.error('Failed to copy JSON:', error);
    }
  };

  return (
    <div className={cn('relative w-full', className)}>
      <CodeBlock code={jsonString} language="json" showLineNumbers={false}>
        {showCopyButton && (
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={handleCopy}
            type="button"
          >
            {copied ? (
              <Check className="h-4 w-4 text-green-500" />
            ) : (
              <Copy className="h-4 w-4" />
            )}
            <span className="sr-only">Copy JSON</span>
          </Button>
        )}
      </CodeBlock>
    </div>
  );
}

