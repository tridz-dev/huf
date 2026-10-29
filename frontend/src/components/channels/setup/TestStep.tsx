import { Check, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';

export interface TestStepProps {
  phone?: string | null;
  done: boolean;
  inboundText: string | null;
  onSkip: () => void;
}

export function TestStep({ phone, done, inboundText, onSkip }: TestStepProps) {
  return (
    <div className="space-y-4">
      <p className="text-sm text-ink">
        From your own phone, send a WhatsApp message to <b>{phone || 'the number you just connected'}</b>. Any text works.
      </p>
      {inboundText && (
        <div className="max-w-sm rounded-lg bg-paper-deep px-3 py-2 text-sm text-ink" aria-label="Message received">
          {inboundText}
        </div>
      )}
      <p role="status" className="flex items-center gap-2 text-sm text-ink">
        {done ? (
          <>
            <Check className="h-4 w-4 text-good" aria-hidden /> Message received. It works.
          </>
        ) : (
          <>
            <Loader2 className="h-4 w-4 animate-spin text-steel" aria-hidden /> Waiting for your message...
          </>
        )}
      </p>
      {!done && (
        <Button variant="ghost" size="sm" onClick={onSkip}>
          Skip the test for now
        </Button>
      )}
    </div>
  );
}
