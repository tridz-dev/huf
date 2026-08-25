/**
 * RightPaneTabStrip — the "Artifact / Analytics" switcher for the shared
 * right-docked pane slot (see ChatPageV2.tsx). The slot previously hosted
 * only `ArtifactPreviewPane`; this pane adds a second, independent tenant
 * (`ConversationAnalyticsPane`) that can be open at the same time. Rather
 * than merging the two panes' chrome (their headers, close buttons, and
 * resize handles stay exactly as each pane already renders them), this is a
 * thin strip mounted above whichever pane is currently visible, purely to
 * switch which one shows. The caller only mounts this component when BOTH
 * tabs have something to show — a single remaining tab is rendered as no
 * strip at all, not a one-item strip.
 */
import { cn } from '@/lib/utils';

export type RightPaneTab = 'artifact' | 'analytics';

export interface RightPaneTabStripProps {
  active: RightPaneTab;
  onSelect: (tab: RightPaneTab) => void;
  width: number;
}

const TABS: { key: RightPaneTab; label: string }[] = [
  { key: 'artifact', label: 'Artifact' },
  { key: 'analytics', label: 'Analytics' },
];

export function RightPaneTabStrip({ active, onSelect, width }: RightPaneTabStripProps) {
  return (
    <div
      className="flex h-8 flex-none items-center gap-1 border-b border-l border-line bg-paper px-2.5"
      style={{ width }}
    >
      {TABS.map((tab) => (
        <button
          key={tab.key}
          type="button"
          onClick={() => onSelect(tab.key)}
          className={cn(
            'rounded-md px-2 py-1 text-[11px] font-medium transition-colors',
            active === tab.key ? 'bg-paper-deep text-ink' : 'text-steel-soft hover:text-steel'
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

export default RightPaneTabStrip;
