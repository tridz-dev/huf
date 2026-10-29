import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { PageFrame } from '@/layouts/PageFrame';
import { ActivityLog } from '../activity/ActivityLog';
import { ConversationsList } from '../activity/ConversationsList';
import { useChannelGateway } from '../useChannelGateway';

type View = 'messages' | 'conversations';

export default function ActivitySection() {
  const gateway = useChannelGateway();
  const [view, setView] = useState<View>('messages');
  const toggle = (
    <div role="group" aria-label="Activity view" className="flex gap-1">
      {(['messages', 'conversations'] as const).map((v) => (
        <Button key={v} size="sm" variant={view === v ? 'secondary' : 'ghost'} aria-pressed={view === v} onClick={() => setView(v)}>
          {v === 'messages' ? 'Messages' : 'Conversations'}
        </Button>
      ))}
    </div>
  );
  return (
    <PageFrame title="Activity" actions={toggle}>
      <div className="p-5">
        {view === 'messages' ? <ActivityLog gateway={gateway} bridgeAvailable /> : <ConversationsList gateway={gateway} />}
      </div>
    </PageFrame>
  );
}
