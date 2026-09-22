import { useState } from 'react';
import { ChevronDown, GitBranch } from 'lucide-react';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

const flushTriggerClass = 'h-auto w-auto justify-start gap-2 rounded-none border-0 bg-transparent px-0 py-0 text-[13.5px] text-ink shadow-none focus:ring-0 focus:ring-offset-0 [&>span]:truncate';

export function DecisionRuntimePreview() {
  const [deployment, setDeployment] = useState('auto');
  return (
    <section className="mb-4 rounded border border-line bg-panel" aria-label="Decision Runtime preview">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <div>
          <div className="flex items-center gap-2 font-mono text-eyebrow uppercase text-steel-soft"><GitBranch className="h-3.5 w-3.5" strokeWidth={1.8} /> Decision Runtime</div>
          <p className="mt-1 text-xs text-steel">Canonical decision model and deployment resolution</p>
        </div>
        <span className="rounded-full border border-line bg-canvas px-2 py-1 font-mono text-[10px] uppercase tracking-wide text-steel-soft">Preview</span>
      </div>
      <div className="grid grid-cols-2 divide-x divide-line md:grid-cols-4">
        <div className="px-4 py-3"><div className="mb-1.5 font-mono text-eyebrow uppercase text-steel-soft">Model</div><div className="font-mono text-[13px] text-ink">Jev 1.13</div></div>
        <div className="px-4 py-3"><div className="mb-1.5 font-mono text-eyebrow uppercase text-steel-soft">Deployment</div><Select value={deployment} onValueChange={setDeployment}><SelectTrigger className={flushTriggerClass} icon={<ChevronDown className="h-3.5 w-3.5 text-steel" strokeWidth={1.8} />}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="auto">Auto</SelectItem><SelectItem value="primary">Primary</SelectItem><SelectItem value="fallback">Fallback</SelectItem></SelectContent></Select></div>
        <div className="px-4 py-3"><div className="mb-1.5 font-mono text-eyebrow uppercase text-steel-soft">Provider</div><div className="font-mono text-[12px] text-steel-soft">Resolved after run</div></div>
        <div className="px-4 py-3"><div className="mb-1.5 font-mono text-eyebrow uppercase text-steel-soft">Provider model ID</div><div className="font-mono text-[12px] text-steel-soft">Resolved after run</div></div>
      </div>
    </section>
  );
}
