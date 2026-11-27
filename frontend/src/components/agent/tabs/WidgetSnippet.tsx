import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';

/** Builds the embed snippet for public/js/huf-voice.js (the only publishable-key script; it is a voice widget). */
export function buildWidgetSnippet(origin: string, publishableKey: string, agentId: string): string {
  const base = origin.replace(/\/$/, '');
  return `<script src="${base}/assets/huf/js/huf-voice.js"></script>
<script>
  var huf = HufVoice.init({
    baseUrl: ${JSON.stringify(base)},
    publishableKey: ${JSON.stringify(publishableKey)},
    agent: ${JSON.stringify(agentId)}
  });
  // Call huf.startSession() from a button click to begin a voice session.
</script>`;
}

export function WidgetSnippet({ publishableKey, agentId }: { publishableKey?: string | null; agentId?: string }) {
  const [copied, setCopied] = useState(false);
  if (!publishableKey || !agentId) {
    return <p className="text-micro text-steel">Save the agent to get an embed snippet.</p>;
  }
  const snippet = buildWidgetSnippet(window.location.origin, publishableKey, agentId);
  const copy = async () => {
    try { await navigator.clipboard.writeText(snippet); setCopied(true); } catch { setCopied(false); }
  };
  return (
    <div className="space-y-1.5">
      <Label htmlFor="widget-snippet">Embed snippet</Label>
      <pre id="widget-snippet" className="overflow-x-auto rounded-md border p-3 text-micro">{snippet}</pre>
      <Button type="button" variant="outline" size="sm" onClick={copy}>{copied ? 'Copied' : 'Copy snippet'}</Button>
      <p className="text-micro text-steel">Adds a voice session starter to your site; the voice channel must be on. Add your site under Allowed domains.</p>
    </div>
  );
}
