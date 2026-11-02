import { Button } from '@/components/ui/button';

export function NotInTelegram({ message, title, onRetry }: { message?: string; title?: string; onRetry?: () => void }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-2 p-6 text-center">
      <h1 className="text-lg font-semibold">{title ?? 'Open this inside Telegram'}</h1>
      <p className="text-sm text-[var(--tg-hint)]">
        {message ?? 'This page is the Huf cockpit Mini App. Open it from your Huf bot in Telegram.'}
      </p>
      {onRetry ? <Button className="mt-2" onClick={onRetry}>Try again</Button> : null}
    </div>
  );
}
