import { Button } from '@/components/ui/button';

export function ChoosePathStep({ onManual }: { onManual: () => void }) {
  return (
    <div className="space-y-3">
      <div className="rounded-md border border-line p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-medium text-ink">Connect with Facebook</p>
            <p className="text-sm text-steel">Recommended. Log in to Meta and pick your number, no copy and paste.</p>
          </div>
          <Button disabled variant="outline" aria-describedby="fb-soon">
            Connect with Facebook
          </Button>
        </div>
        <p id="fb-soon" className="mt-2 text-xs text-steel">
          Coming soon.
        </p>
      </div>
      <div className="rounded-md border border-line p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-medium text-ink">I have a Meta app</p>
            <p className="text-sm text-steel">Paste the IDs and keys from your Meta developer dashboard.</p>
          </div>
          <Button onClick={onManual}>I have a Meta app</Button>
        </div>
      </div>
    </div>
  );
}
