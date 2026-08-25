import { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { ChevronRight, Loader2, Pencil, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import { improvePrompt } from '@/services/consoleApi';
import { wordDiff } from './wordDiff';
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
  const [improving, setImproving] = useState(false);
  const [improvedPrompt, setImprovedPrompt] = useState<string | null>(null);

  // Auto-expand the disclosure when criteria arrive from outside (e.g. a
  // restored ledger entry or a loaded template).
  const hadCriteria = useRef(!!config.evaluationCriteria.trim());
  useEffect(() => {
    const has = !!config.evaluationCriteria.trim();
    if (has && !hadCriteria.current) setCriteriaOpen(true);
    hadCriteria.current = has;
  }, [config.evaluationCriteria]);

  const handleImprove = async () => {
    if (!config.prompt.trim()) {
      toast.info('Write a prompt first, then use Improve prompt.');
      return;
    }
    setImproving(true);
    try {
      const result = await improvePrompt({
        prompt_body: config.prompt,
        provider: config.provider || undefined,
        model: config.model || undefined,
      });
      setImprovedPrompt(result.prompt);
    } catch {
      // The service already surfaces the error toast.
    } finally {
      setImproving(false);
    }
  };

  const handleAcceptImprovement = () => {
    if (improvedPrompt === null) return;
    onConfigChange({ ...config, prompt: improvedPrompt });
    setImprovedPrompt(null);
    toast.success('Improved prompt applied');
  };

  const handleDiscardImprovement = () => setImprovedPrompt(null);

  const diff = improvedPrompt !== null ? wordDiff(config.prompt, improvedPrompt) : null;

  return (
    <div className={cn('flex min-h-[260px] flex-col rounded border border-line bg-panel', className)}>
      <div className="flex items-center justify-between border-b border-line px-3.5 py-2.5">
        <span className="font-mono text-eyebrow font-medium uppercase text-steel">Prompt</span>
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={handleImprove}
            title="Improve prompt"
            aria-label="Improve prompt"
            className="h-auto w-auto p-0 text-steel hover:bg-transparent hover:text-ink disabled:opacity-40"
            disabled={improving || improvedPrompt !== null}
          >
            {improving ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Sparkles className="h-4 w-4" strokeWidth={1.8} />
            )}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={onDraft}
            title="Draft prompt"
            aria-label="Draft prompt"
            className="h-auto w-auto p-0 text-steel hover:bg-transparent hover:text-ink disabled:opacity-40"
            disabled={generating}
          >
            {generating ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Pencil className="h-4 w-4" strokeWidth={1.8} />
            )}
          </Button>
        </div>
      </div>

      {improvedPrompt !== null && diff ? (
        <div className="flex min-h-0 flex-1 flex-col divide-y divide-line overflow-y-auto">
          <div className="px-3.5 py-2.5">
            <div className="mb-1 font-mono text-[11px] uppercase text-steel-soft">Current</div>
            <p className="whitespace-pre-wrap text-[12.5px] leading-relaxed">
              {diff.a.map((segment, index) => (
                <span
                  key={index}
                  className={cn(
                    segment.type === 'removed' && 'bg-red-100 text-red-900 line-through decoration-red-400',
                  )}
                >
                  {segment.text}
                </span>
              ))}
            </p>
          </div>
          <div className="px-3.5 py-2.5">
            <div className="mb-1 font-mono text-[11px] uppercase text-steel-soft">Improved</div>
            <p className="whitespace-pre-wrap text-[12.5px] leading-relaxed">
              {diff.b.map((segment, index) => (
                <span
                  key={index}
                  className={cn(segment.type === 'added' && 'bg-emerald-100 text-emerald-900')}
                >
                  {segment.text}
                </span>
              ))}
            </p>
          </div>
        </div>
      ) : (
        <Textarea
          value={config.prompt}
          onChange={(e) => onConfigChange({ ...config, prompt: e.target.value })}
          placeholder="Type a prompt to send to the agent…"
          className="min-h-0 flex-1 resize-none rounded border-0 px-3.5 py-3 font-sans text-[13.5px] leading-relaxed shadow-sm placeholder:text-steel focus-visible:ring-0"
        />
      )}

      {improvedPrompt !== null && (
        <div className="flex items-center justify-end gap-2 border-t border-line px-3.5 py-2">
          <Button type="button" variant="outline" size="sm" onClick={handleDiscardImprovement}>
            Discard
          </Button>
          <Button type="button" size="sm" onClick={handleAcceptImprovement}>
            Accept
          </Button>
        </div>
      )}

      <div className="border-t border-line px-3.5 py-2.5">
        <Button
          type="button"
          variant="ghost"
          onClick={() => setCriteriaOpen((open) => !open)}
          aria-expanded={criteriaOpen}
          className="h-auto items-center gap-1.5 p-0 text-[12.5px] text-steel hover:bg-transparent hover:text-ink"
        >
          <ChevronRight
            className={cn('h-3.5 w-3.5 transition-transform', criteriaOpen && 'rotate-90')}
            strokeWidth={1.8}
          />
          Evaluation criteria
        </Button>
        {criteriaOpen && (
          <Textarea
            value={config.evaluationCriteria}
            onChange={(e) => onConfigChange({ ...config, evaluationCriteria: e.target.value })}
            placeholder="Describe what a good response must include…"
            className="mt-2 min-h-[72px] resize-none rounded border-line px-2.5 py-2 text-[12.5px] shadow-sm focus-visible:ring-1"
          />
        )}
      </div>
    </div>
  );
}
