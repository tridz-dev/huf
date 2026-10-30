import { useState } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { PageFrame } from '@/layouts/PageFrame';
import { ActivityLog } from '../activity/ActivityLog';
import { ConversationThread } from '../activity/ConversationThread';
import { ConversationsList } from '../activity/ConversationsList';
import { useChannel, useChannelGateway } from '../useChannelGateway';

type View = 'messages' | 'conversations';

export default function ActivitySection() {
  const gateway = useChannelGateway();
  const channel = useChannel();
  const { conversationId } = useParams();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [reloadKey, setReloadKey] = useState(0);
  const base = pathname.replace(/\/activity(\/.*)?$/, '/activity');
  const [chosen, setView] = useState<View>('conversations');
  // The raw message log is the WhatsApp event stream; other channels show conversations only.
  const view: View = channel === 'whatsapp' ? chosen : 'conversations';
  const toggle = channel !== 'whatsapp' ? undefined : (
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
      {view === 'messages' ? (
        <div className="p-5"><ActivityLog gateway={gateway} bridgeAvailable /></div>
      ) : (
        <div className="flex h-[calc(100vh-9rem)] min-h-[24rem] border-t border-line">
          <div className={cn('w-full shrink-0 border-r border-line min-[900px]:block min-[900px]:w-80', conversationId ? 'hidden' : 'block')}>
            <ConversationsList gateway={gateway} selected={conversationId} reloadKey={reloadKey} onSelect={(n) => navigate(`${base}/${encodeURIComponent(n)}`)} />
          </div>
          <div className={cn('min-w-0 flex-1 min-[900px]:block', conversationId ? 'block' : 'hidden')}>
            {conversationId ? (
              <div className="flex h-full flex-col">
                <div className="min-[900px]:hidden">
                  <Button size="sm" variant="ghost" onClick={() => navigate(base)}>Back</Button>
                </div>
                <div className="min-h-0 flex-1">
                  <ConversationThread key={conversationId} name={conversationId} onChanged={() => setReloadKey((k) => k + 1)} />
                </div>
              </div>
            ) : (
              <p className="p-6 text-center text-xs text-steel">Select a conversation.</p>
            )}
          </div>
        </div>
      )}
    </PageFrame>
  );
}
