import { Button } from '@/components/ui/button';

const STEPS = ['Add documents', 'We prepare them', 'Test and attach to an agent'];

export function LibraryEmptyState({ onUpload, onConnect }: { onUpload: () => void; onConnect: () => void }) {
  return (
    <div className="mx-auto max-w-2xl rounded-lg border border-border p-8 text-center space-y-5">
      <h2 className="text-xl font-semibold">Teach your agents with your own documents.</h2>
      <p className="text-steel">Upload files, connect a folder or a bucket, and ask questions to check the answers.</p>
      <div className="flex flex-wrap justify-center gap-2">
        <Button onClick={onUpload}>Add content</Button>
        <Button variant="outline" onClick={onConnect}>Connect storage</Button>
      </div>
      <ol className="grid gap-3 pt-3 text-sm text-steel sm:grid-cols-3">
        {STEPS.map((s, i) => (
          <li key={s} className="rounded-md bg-muted/40 p-3"><span className="font-semibold">{i + 1}.</span> {s}</li>
        ))}
      </ol>
    </div>
  );
}
