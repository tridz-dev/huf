import { useEffect, useState } from 'react';
import { onAnnounce } from '@/lib/flow-history/announce';

/** One polite live region for the editor: what Undo, Redo, Duplicate and Paste just did, for screen readers. Visually hidden. */
export function FlowLiveRegion() {
  const [message, setMessage] = useState('');
  useEffect(() => onAnnounce(setMessage), []);
  return (
    <div role="status" aria-live="polite" aria-atomic="true" className="sr-only" data-testid="flow-live-region">
      {message}
    </div>
  );
}
