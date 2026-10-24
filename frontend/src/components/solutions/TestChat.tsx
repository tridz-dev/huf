import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import { TraceList } from './TraceList';
import { useTestChat } from './useTestChat';

export interface TestChatGateway {
  name: string;
  label: string;
  phone: string;
}

export interface TestChatProps {
  gateways: TestChatGateway[];
  gateway?: string;
  onGatewayChange?: (gateway: string) => void;
  chips?: string[];
  /** Ad / link tags shown as "Tap ad <tag>" chips. */
  adChips?: string[];
  embedded?: boolean;
  brand?: string;
  solutionLabels?: Record<string, string>;
}

const nativeSelect =
  'h-9 rounded-md border border-input bg-background px-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring';

export function TestChat({
  gateways,
  gateway,
  onGatewayChange,
  chips = [],
  adChips = [],
  embedded = false,
  brand = 'Your business',
  solutionLabels,
}: TestChatProps) {
  const [localGateway, setLocalGateway] = useState(gateway ?? gateways[0]?.name ?? '');
  const active = gateway ?? localGateway;
  const current = gateways.find((g) => g.name === active);
  const chat = useTestChat({ gateway: active, solutionLabels });
  const [draft, setDraft] = useState('');
  const [target, setTarget] = useState('');
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scroller.current?.scrollTo?.({ top: scroller.current.scrollHeight });
  }, [chat.messages.length]);

  const options = chat.handOffOptions;
  const selected = options.includes(target) ? target : (options[0] ?? '');

  const changeGateway = (name: string) => {
    setLocalGateway(name);
    chat.clear();
    onGatewayChange?.(name);
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const text = draft;
    setDraft('');
    void chat.send(text);
  };

  return (
    <div className={cn('grid gap-4', embedded ? 'grid-cols-1' : 'lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]')}>
      <div>
        <div className="mb-2 flex items-center gap-2">
          <label htmlFor="testchat-number" className="text-sm text-steel">
            Customer messages
          </label>
          <select
            id="testchat-number"
            className={nativeSelect}
            value={active}
            onChange={(e) => changeGateway(e.target.value)}
          >
            {gateways.map((g) => (
              <option key={g.name} value={g.name}>
                {g.label} {g.phone}
              </option>
            ))}
          </select>
        </div>
        <Card className="overflow-hidden">
          <div className="border-b px-4 py-3">
            <div className="font-semibold">{brand}</div>
            <div className="text-xs text-steel">{current?.label ?? active} · business account</div>
          </div>
          <div ref={scroller} className="flex h-72 flex-col gap-2 overflow-y-auto bg-muted p-3" aria-live="polite">
            {chat.messages.length === 0 ? (
              <div className="m-auto text-xs text-steel">No messages yet</div>
            ) : (
              chat.messages.map((m) =>
                m.from === 'sys' ? (
                  <div key={m.id} className="self-center text-xs text-steel">
                    {m.text}
                  </div>
                ) : (
                  <div
                    key={m.id}
                    data-from={m.from}
                    className={cn(
                      'max-w-[80%] rounded-lg px-3 py-2 text-sm',
                      m.from === 'me'
                        ? 'self-end bg-primary text-primary-foreground'
                        : 'self-start border bg-card text-foreground',
                    )}
                  >
                    {m.who ? <div className="mb-0.5 text-[11px] text-steel">{m.who}</div> : null}
                    {m.text}
                  </div>
                ),
              )
            )}
            {chat.loading ? <div className="self-start text-xs text-steel">Routing...</div> : null}
          </div>
          {chat.error ? (
            <div role="alert" className="border-t px-3 py-2 text-sm text-destructive">
              {chat.error}
            </div>
          ) : null}
          {chips.length + adChips.length > 0 ? (
            <div className="flex flex-wrap gap-1.5 border-t px-3 py-2">
              {chips.map((c) => (
                <Button key={c} type="button" size="sm" variant="outline" onClick={() => void chat.send(c)}>
                  {c}
                </Button>
              ))}
              {adChips.map((tag) => (
                <Button key={`ad:${tag}`} type="button" size="sm" variant="outline" onClick={() => void chat.send('', tag)}>
                  Tap ad {tag}
                </Button>
              ))}
            </div>
          ) : null}
          <form onSubmit={submit} className="flex gap-2 border-t p-3">
            <Input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Type as the customer"
              aria-label="Message"
            />
            <Button type="submit" disabled={chat.loading}>
              Send
            </Button>
          </form>
        </Card>
        <div className="mt-2 flex items-center justify-between text-xs text-steel">
          <span>Simulation only. Nothing is sent.</span>
          <Button type="button" size="sm" variant="ghost" onClick={chat.clear}>
            Clear chat
          </Button>
        </div>
      </div>

      <div className="flex flex-col gap-4">
        <Card className="p-4">
          <h3 className="font-semibold">Chat pin</h3>
          {chat.pin ? (
            <>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <Badge variant="secondary">{chat.labelOf(chat.pin.solution)}</Badge>
                <span className="font-mono text-xs text-steel">
                  {chat.pin.hoursLeft > 0 ? `${chat.pin.hoursLeft}h left` : 'expired'}
                </span>
                <Button type="button" size="sm" variant="outline" onClick={chat.expire}>
                  Skip 25 hours
                </Button>
              </div>
              <div className="mt-3 flex items-center gap-2">
                <label htmlFor="testchat-handoff" className="text-sm text-steel">
                  Hand off to
                </label>
                <select
                  id="testchat-handoff"
                  className={nativeSelect}
                  value={selected}
                  onChange={(e) => setTarget(e.target.value)}
                  disabled={options.length === 0}
                >
                  {options.length === 0 ? <option value="">No other</option> : null}
                  {options.map((s) => (
                    <option key={s} value={s}>
                      {chat.labelOf(s)}
                    </option>
                  ))}
                </select>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={!selected}
                  onClick={() => chat.handOff(selected)}
                >
                  Hand off
                </Button>
              </div>
            </>
          ) : (
            <p className="mt-2 text-sm text-steel">No pin yet. The first match pins the customer for 24 hours.</p>
          )}
          <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={chat.keywordBeatsPin}
              onChange={(e) => chat.setKeywordBeatsPin(e.target.checked)}
            />
            Keyword beats the pin (flip to compare)
          </label>
        </Card>
        <Card className="p-4">
          <h3 className="mb-2 font-semibold">Why it routed that way</h3>
          <TraceList trace={chat.trace} />
        </Card>
      </div>
    </div>
  );
}
