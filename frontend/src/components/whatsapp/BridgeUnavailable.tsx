import { PlugZap } from 'lucide-react';

export function BridgeUnavailable() {
  return (
    <div role="status" className="flex flex-col items-center gap-2 rounded-sm border border-line p-10 text-center">
      <PlugZap className="h-6 w-6 text-steel" />
      <h3 className="text-sm font-semibold text-ink">WhatsApp bridge not available</h3>
      <p className="max-w-md text-xs text-steel">
        Templates and message history need the optional WhatsApp Business app connector installed on this site.
        Install it, then reload. Ask your administrator if you are unsure how.
      </p>
    </div>
  );
}

export function LoadError({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex items-center justify-between gap-3 rounded-sm border border-destructive p-3 text-xs text-destructive">
      <span>{message}</span>
      {onRetry && (
        <button type="button" className="underline" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}
