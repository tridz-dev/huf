import { Input } from '@/components/ui/input';
import { reasonText } from '../plainText';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { AudiencePicker } from '../../audiences/AudiencePicker';
import type { AudienceSelectionItem, SelectionPreview } from '../../audiences/audiencesApi';
import type { AddRecipientsResult } from '../broadcastApi';
import { previewAudienceSelectionForGateway } from './audienceSelectionApi';

export function ResultBlock({ result, label }: { result: AddRecipientsResult; label?: string }) {
  return (
    <div role="status" className="rounded-md border p-3 text-sm">
      <p><strong>{result.added}</strong> recipients added{label ? ` ${label}` : ''}.</p>
      {result.invalidTotal ? (
        <div><p>{result.invalidTotal} invalid{result.invalidTotal > result.invalid.length ? ` (showing ${result.invalid.length})` : ''}:</p>
          <ul className="list-disc pl-5">{result.invalid.map((x, i) => <li key={i}>{x.recipient ?? ''}{x.reason ? `: ${reasonText(x.reason)}` : ''}</li>)}</ul></div>
      ) : null}
      {result.skippedTotal ? (
        <div><p>{result.skippedTotal} skipped{result.skippedTotal > result.skipped.length ? ` (showing ${result.skipped.length})` : ''}:</p>
          <ul className="list-disc pl-5">{result.skipped.map((x, i) => <li key={i}>{x.recipient}: {reasonText(x.reason)}</li>)}</ul></div>
      ) : null}
    </div>
  );
}

interface Props {
  gateway: string;
  templateCategory?: string;
  selection: AudienceSelectionItem[];
  onSelection: (s: AudienceSelectionItem[]) => void;
  onAudiencePreview: (p: SelectionPreview | null) => void;
  text: string;
  onText: (t: string) => void;
  csv: string | null;
  onFile: (f: File | undefined) => void;
  locked: boolean;
  columnsHint: string;
  result: AddRecipientsResult | null;
  listsResult: AddRecipientsResult | null;
}

/** Recipients step: saved lists (with live counts) and/or numbers for just this broadcast. Both can be combined. */
export function RecipientsStep(p: Props) {
  const none = (p.result?.added ?? 0) + (p.listsResult?.added ?? 0) === 0;
  return (
    <div className="space-y-4">
      <section aria-label="Saved lists" className="space-y-2">
        <h3 className="text-sm font-medium">Saved lists</h3>
        <div className={p.locked ? 'pointer-events-none opacity-60' : undefined} aria-disabled={p.locked}>
          <AudiencePicker
            gateway={p.gateway}
            value={p.selection}
            onChange={p.onSelection}
            onPreview={p.onAudiencePreview}
            previewer={(sel) => previewAudienceSelectionForGateway(p.gateway, sel, p.templateCategory)}
            previewKey={p.templateCategory ?? ''}
          />
        </div>
      </section>
      <section aria-label="Just for this broadcast" className="space-y-3">
        <h3 className="text-sm font-medium">Just for this broadcast</h3>
        <div className="space-y-1">
          <Label htmlFor="bc-recipients">Recipients (one phone number per line)</Label>
          <Textarea id="bc-recipients" rows={8} value={p.text} disabled={p.locked || p.csv !== null} onChange={(e) => p.onText(e.target.value)} placeholder="+14155550101" />
          <p className="text-xs text-steel">{p.columnsHint}</p>
        </div>
        <div className="space-y-1">
          <Label htmlFor="bc-csv">Or upload a CSV (header: phone)</Label>
          <Input id="bc-csv" type="file" accept=".csv,text/csv" disabled={p.locked} onChange={(e) => p.onFile(e.target.files?.[0])} />
          {p.csv !== null ? <p className="text-xs text-steel">CSV loaded ({p.csv.split('\n').length - 1} rows)</p> : null}
        </div>
      </section>
      {p.result ? <ResultBlock result={p.result} /> : null}
      {p.listsResult ? <ResultBlock result={p.listsResult} label="from saved lists" /> : null}
      {(p.result || p.listsResult) && none ? <p role="status" className="text-sm text-destructive">No valid recipients. Fix the list and try again.</p> : null}
    </div>
  );
}
