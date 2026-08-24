import { FileText, Gavel, ListChecks, ListTree } from 'lucide-react';
import { Streamdown } from 'streamdown';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

interface MeetingSummaryPanelProps {
  /**
   * Markdown produced by the "Meeting Summary Agent" (huf/install.py
   * MEETING_SUMMARY_INSTRUCTIONS): exactly three `## ` sections in order —
   * Headline, Key Points, Action Items.
   */
  summary?: string | null;
}

interface ParsedSummary {
  headline: string;
  keyPoints: string;
  decisions: string;
  actionItems: string;
}

const SECTION_HEADINGS = ['Headline', 'Key Points', 'Decisions', 'Action Items'] as const;

/**
 * Splits the agent's Markdown output into its three named `## ` sections.
 * Deliberately tolerant of missing/reordered/extra sections — the model
 * output is not guaranteed to match the prompt exactly, and a blank block
 * is a better failure mode than a crash or a wall of unstructured text.
 */
function parseSummary(markdown: string): ParsedSummary {
  const sections: Record<string, string> = {};
  const matches = markdown.split(/(^##\s+.+$)/m);

  let currentHeading: string | null = null;
  for (const part of matches) {
    const headingMatch = part.match(/^##\s+(.+)$/m);
    if (headingMatch) {
      currentHeading = headingMatch[1].trim();
      continue;
    }
    if (currentHeading) {
      sections[currentHeading] = (sections[currentHeading] || '') + part;
    }
  }

  return {
    headline: sections['Headline']?.trim() || '',
    keyPoints: sections['Key Points']?.trim() || '',
    decisions: sections['Decisions']?.trim() || '',
    actionItems: sections['Action Items']?.trim() || '',
  };
}

/**
 * Headline + Key Points + Action Items rendered as three distinct blocks
 * (PLAN.md G.1 "summary readability" — not one undifferentiated paragraph).
 * Falls back to rendering the raw markdown if the expected `## ` sections
 * aren't found, so an off-spec agent response still shows something useful.
 */
export function MeetingSummaryPanel({ summary }: MeetingSummaryPanelProps) {
  if (!summary || !summary.trim()) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-line py-10 text-center">
        <FileText className="h-5 w-5 text-steel-soft" aria-hidden />
        <p className="font-body text-sm text-steel">Meeting has no summary yet.</p>
      </div>
    );
  }

  const parsed = parseSummary(summary);
  const hasStructuredSections = SECTION_HEADINGS.some(
    (heading) => heading === 'Headline' ? parsed.headline : heading === 'Key Points' ? parsed.keyPoints : heading === 'Decisions' ? parsed.decisions : parsed.actionItems,
  );

  if (!hasStructuredSections) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Summary</CardTitle>
        </CardHeader>
        <CardContent className="prose prose-sm max-w-none">
          <Streamdown>{summary}</Streamdown>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {parsed.headline && (
        <div className="rounded-lg border border-line bg-card px-5 py-4">
          <h2 className="font-body text-[15px] font-medium leading-snug text-ink">{parsed.headline}</h2>
        </div>
      )}

      {parsed.keyPoints && (
        <Card>
          <CardHeader className="flex flex-row items-center gap-2 space-y-0">
            <ListTree className="h-4 w-4 text-steel-soft" aria-hidden />
            <CardTitle className="text-sm">Key points</CardTitle>
          </CardHeader>
          <CardContent className="prose prose-sm max-w-none [&_ul]:my-0 [&_li]:my-1">
            <Streamdown>{parsed.keyPoints}</Streamdown>
          </CardContent>
        </Card>
      )}

      {parsed.decisions && (
        <Card>
          <CardHeader className="flex flex-row items-center gap-2 space-y-0">
            <Gavel className="h-4 w-4 text-steel-soft" aria-hidden />
            <CardTitle className="text-sm">Decisions</CardTitle>
          </CardHeader>
          <CardContent className="prose prose-sm max-w-none [&_ul]:my-0 [&_li]:my-1">
            <Streamdown>{parsed.decisions}</Streamdown>
          </CardContent>
        </Card>
      )}

      {parsed.actionItems && (
        <Card>
          <CardHeader className="flex flex-row items-center gap-2 space-y-0">
            <ListChecks className="h-4 w-4 text-steel-soft" aria-hidden />
            <CardTitle className="text-sm">Action items</CardTitle>
          </CardHeader>
          <CardContent
            className="prose prose-sm max-w-none [&_ul]:list-none [&_ul]:pl-0 [&_ul]:my-0 [&_li]:my-1.5 [&_li]:flex [&_li]:items-start [&_li]:gap-2 [&_li::before]:content-['\2610'] [&_li::before]:text-steel-soft [&_li::before]:leading-[1.4]"
          >
            <Streamdown>{parsed.actionItems}</Streamdown>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
