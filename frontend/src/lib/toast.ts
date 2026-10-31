/**
 * Flow editor toasts: success disappears after 3 s, errors after 6 s (long enough to read the reason),
 * plain messages (with an Undo action) after 5 s, info after 4 s, warnings after 8 s. All are dismissible (the Toaster shows a close button). A caller can still pass its own `duration`.
 */
import { toast as base, type ExternalToast } from 'sonner';

type Message = Parameters<typeof base>[0];

const DURATION = { success: 3000, error: 6000, info: 4000, warning: 8000, message: 5000 } as const;

const withDuration = (fn: (m: Message, d?: ExternalToast) => string | number, ms: number) =>
  (message: Message, data?: ExternalToast) => fn(message, { duration: ms, ...data });

export const toast = Object.assign(withDuration(base as never, DURATION.message), base, {
  success: withDuration(base.success, DURATION.success),
  error: withDuration(base.error, DURATION.error),
  info: withDuration(base.info, DURATION.info),
  warning: withDuration(base.warning, DURATION.warning),
});
