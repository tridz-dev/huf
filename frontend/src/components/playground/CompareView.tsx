import { useMemo, useState } from 'react';
import { ArrowRightLeft, Copy, GitCompare, Pencil } from 'lucide-react';
import type { AgentDoc, AIProvider } from '@/types/agent.types';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { ShortcutKey } from '@/components/ui/shortcut-key';
import { useKeyboardShortcut } from '@/lib/shortcuts/useKeyboardShortcut';
import { formatBinding } from '@/lib/shortcuts/registry';
import { usePlatform } from '@/lib/shortcuts/platform';
import { ConfigStrip } from './ConfigStrip';
import { PromptPanel } from './PromptPanel';
import { ResponsePanel } from './ResponsePanel';
import { RunLedger, type RunLedgerProps } from './RunLedger';
import { wordDiff } from './wordDiff';
import type { PlaygroundConfig, SlotState } from './types';

const COPY_A_TO_B_BINDING = { key: 'c', mod: true, shift: true } as const;
const SWAP_BINDING = { key: 'x', mod: true, shift: true } as const;
const TOGGLE_DIFF_BINDING = { key: 'd', mod: true, shift: true } as const;

interface CompareViewProps {
  agents: AgentDoc[];
  providers: AIProvider[];
  configA: PlaygroundConfig;
  configB: PlaygroundConfig;
  onConfigAChange: (config: PlaygroundConfig) => void;
  onConfigBChange: (config: PlaygroundConfig) => void;
  slotA: SlotState;
  slotB: SlotState;
  onRunA: () => void;
  onRunB: () => void;
  onDraftA: () => void;
  onDraftB: () => void;
  ledger: RunLedgerProps;
}

interface EditableLabelProps {
  glyph: string;
  label: string;
  onLabelChange: (label: string) => void;
}

function EditableLabel({ glyph, label, onLabelChange }: EditableLabelProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(label);
  const isColumnA = glyph === 'A';

  const commit = () => {
    const trimmed = draft.trim();
    if (trimmed) onLabelChange(trimmed);
    setEditing(false);
  };

  return (
    <div className="mb-2 flex items-center gap-2">
      <span
        className={cn(
          'inline-flex h-[18px] w-[18px] items-center justify-center rounded-[6px] text-[11px] font-medium',
          isColumnA ? 'bg-ink text-paper' : 'bg-signal text-white',
        )}
      >
        {glyph}
      </span>
      {editing ? (
        <input
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === 'Enter') commit();
            if (e.key === 'Escape') {
              setDraft(label);
              setEditing(false);
            }
          }}
          aria-label={`Label for column ${glyph}`}
          className="w-32 border-b border-dashed border-ink bg-transparent text-[12.5px] text-ink outline-none"
        />
      ) : (
        <Button
          type="button"
          variant="ghost"
          onClick={() => {
            setDraft(label);
            setEditing(true);
          }}
          className="h-auto gap-1.5 p-0 text-[12.5px] font-normal text-steel hover:bg-transparent hover:text-ink"
        >
          <span className="border-b border-dashed border-line">{label}</span>
          <Pencil className="h-3 w-3 text-steel-soft" strokeWidth={1.8} />
        </Button>
      )}
    </div>
  );
}

export function CompareView({
  agents,
  providers,
  configA,
  configB,
  onConfigAChange,
  onConfigBChange,
  slotA,
  slotB,
  onRunA,
  onRunB,
  onDraftA,
  onDraftB,
  ledger,
}: CompareViewProps) {
  const [labelA, setLabelA] = useState('Baseline');
  const [labelB, setLabelB] = useState('Challenger');
  const [diffEnabled, setDiffEnabled] = useState(true);
  const platform = usePlatform();

  const diff = useMemo(() => {
    if (!diffEnabled) return null;
    const responseA = slotA.result?.response;
    const responseB = slotB.result?.response;
    if (!responseA || !responseB || !slotA.result?.success || !slotB.result?.success) {
      return null;
    }
    return wordDiff(responseA, responseB);
  }, [diffEnabled, slotA.result, slotB.result]);

  const handleCopyAtoB = () => {
    onConfigBChange({ ...configA });
  };

  const handleSwap = () => {
    const nextA = configB;
    const nextB = configA;
    onConfigAChange(nextA);
    onConfigBChange(nextB);
    const nextLabelA = labelB;
    const nextLabelB = labelA;
    setLabelA(nextLabelA);
    setLabelB(nextLabelB);
  };

  const toggleDiff = () => setDiffEnabled((on) => !on);

  useKeyboardShortcut(COPY_A_TO_B_BINDING, handleCopyAtoB, { allowInEditable: true });
  useKeyboardShortcut(SWAP_BINDING, handleSwap, { allowInEditable: true });
  useKeyboardShortcut(TOGGLE_DIFF_BINDING, toggleDiff, { allowInEditable: true });

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto">
      <div className="flex items-center px-5 pt-3">
        <div className="flex items-center gap-2 font-mono text-eyebrow uppercase text-steel-soft">
          Two configurations
        </div>
      </div>

      {/* Columns, with a center console acting on both */}
      <div className="grid flex-1 grid-cols-1 gap-4 p-5 lg:grid-cols-[1fr_auto_1fr] lg:items-stretch">
        <div>
          <EditableLabel glyph="A" label={labelA} onLabelChange={setLabelA} />
          <ConfigStrip
            compact
            agents={agents}
            providers={providers}
            config={configA}
            onChange={onConfigAChange}
          />
          <PromptPanel
            config={configA}
            onConfigChange={onConfigAChange}
            onDraft={onDraftA}
            generating={slotA.generating}
            className="mt-4 min-h-[170px]"
          />
          <ResponsePanel
            title="Response A"
            state={slotA}
            diffSegments={diff?.a ?? null}
            runLabel="Run A"
            onRun={onRunA}
            className="mt-4 min-h-[170px]"
          />
        </div>

        <div className="flex flex-row items-center justify-center gap-3 border-y border-line py-2 lg:h-full lg:w-14 lg:flex-col lg:justify-center lg:gap-4 lg:border-x lg:border-y-0 lg:py-4">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                onClick={handleCopyAtoB}
                aria-label="Copy A to B"
                className="text-steel hover:bg-paper-deep hover:text-ink"
              >
                <Copy className="h-3.5 w-3.5" strokeWidth={1.8} />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right" className="flex items-center gap-2">
              <span>Copy A → B</span>
              <ShortcutKey keys={formatBinding(COPY_A_TO_B_BINDING, platform)} size="sm" />
            </TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                onClick={handleSwap}
                aria-label="Swap A and B"
                className="text-steel hover:bg-paper-deep hover:text-ink"
              >
                <ArrowRightLeft className="h-3.5 w-3.5" strokeWidth={1.8} />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right" className="flex items-center gap-2">
              <span>Swap A and B</span>
              <ShortcutKey keys={formatBinding(SWAP_BINDING, platform)} size="sm" />
            </TooltipContent>
          </Tooltip>

          <div className="h-6 w-px bg-line lg:h-px lg:w-6" />

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                role="switch"
                aria-checked={diffEnabled}
                aria-label="Toggle diff responses"
                onClick={toggleDiff}
                className={cn(
                  'hover:bg-paper-deep',
                  diffEnabled ? 'text-signal' : 'text-steel',
                )}
              >
                <GitCompare className="h-3.5 w-3.5" strokeWidth={1.8} />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right" className="flex items-center gap-2">
              <span>Diff responses: {diffEnabled ? 'on' : 'off'}</span>
              <ShortcutKey keys={formatBinding(TOGGLE_DIFF_BINDING, platform)} size="sm" />
            </TooltipContent>
          </Tooltip>
        </div>

        <div>
          <EditableLabel glyph="B" label={labelB} onLabelChange={setLabelB} />
          <ConfigStrip
            compact
            agents={agents}
            providers={providers}
            config={configB}
            onChange={onConfigBChange}
          />
          <PromptPanel
            config={configB}
            onConfigChange={onConfigBChange}
            onDraft={onDraftB}
            generating={slotB.generating}
            className="mt-4 min-h-[170px]"
          />
          <ResponsePanel
            title="Response B"
            state={slotB}
            diffSegments={diff?.b ?? null}
            runLabel="Run B"
            onRun={onRunB}
            className="mt-4 min-h-[170px]"
          />
        </div>
      </div>

      <div className="px-5 pb-[18px]">
        <RunLedger {...ledger} />
      </div>
    </div>
  );
}
