import { useEffect, useRef, useState } from 'react';
import { ChevronRight, Loader2, Pencil } from 'lucide-react';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import type { PlaygroundConfig } from './types';

interface PromptPanelProps {
  config: PlaygroundConfig;
  onConfigChange: (config: PlaygroundConfig) => void;
  onDraft: () => void;
  generating: boolean;
  className?: string;
}

export function PromptPanel({
  config,
  onConfigChange,
  onDraft,
  generating,
  className,
}: PromptPanelProps) {
  const [criteriaOpen, setCriteriaOpen] = useState(() => !!config.evaluationCriteria.trim());

  // Auto-expand the disclosure when criteria arrive from outside (e.g. a
  // restored ledger entry or a loaded template).
  const hadCriteria = useRef(!!config.evaluationCriteria.trim());
  useEffect(() => {
    const has = !!config.evaluationCriteria.trim();
    if (has && !hadCriteria.current) setCriteriaOpen(true);
    hadCriteria.current = has;
  }, [config.evaluationCriteria]);

  return (
    <div className={cn('flex min-h-[260px] flex-col rounded border border-line bg-panel', className)}>
      <div className="flex items-center justify-between border-b border-line px-3.5 py-2.5">
        <span className="font-display text-[15px] font-bold uppercase">Prompt</span>
        <button
          type="button"
          onClick={onDraft}
          title="Draft prompt"
          aria-label="Draft prompt"
          className="text-steel transition-colors hover:text-ink disabled:opacity-40"
          disabled={generating}
        >
          {generating ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Pencil className="h-4 w-4" strokeWidth={1.8} />
          )}
        </button>
      </div>

      <Textarea
        value={config.prompt}
        onChange={(e) => onConfigChange({ ...config, prompt: e.target.value })}
        placeholder="Type a prompt to send to the agent…"
        className="min-h-0 flex-1 resize-none rounded-none border-0 px-3.5 py-3 font-sans text-[13.5px] leading-relaxed shadow-none placeholder:text-steel focus-visible:ring-0"
      />

      <div className="border-t border-line px-3.5 py-2.5">
        <button
          type="button"
          onClick={() => setCriteriaOpen((open) => !open)}
          aria-expanded={criteriaOpen}
          className="flex items-center gap-1.5 text-[12.5px] text-steel transition-colors hover:text-ink"
        >
          <ChevronRight
            className={cn('h-3.5 w-3.5 transition-transform', criteriaOpen && 'rotate-90')}
            strokeWidth={1.8}
          />
          Evaluation criteria
        </button>
        {criteriaOpen && (
          <Textarea
            value={config.evaluationCriteria}
            onChange={(e) => onConfigChange({ ...config, evaluationCriteria: e.target.value })}
            placeholder="Describe what a good response must include…"
            className="mt-2 min-h-[72px] resize-none rounded border-line px-2.5 py-2 text-[12.5px] shadow-none focus-visible:ring-1"
          />
        )}
      </div>
    </div>
  );
}
