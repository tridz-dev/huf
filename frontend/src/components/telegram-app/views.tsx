import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  approvals as fetchApprovals, audit as fetchAudit, digest as fetchDigest, getDocSummary, me as fetchMe,
  revokeToken, search as runSearch, TelegramAppError,
  type TgApprovalItem, type TgAudit, type TgConfig, type TgDigest, type TgDocSummary, type TgMe, type TgSearchItem,
} from '@/services/telegramAppApi';
import { ActionPanel } from './ActionPanel';
import { DoctypePicker } from './DoctypePicker';
import { doctypeChoices, formatFieldValue } from './model';

export type DocRef = { doctype: string; name: string };

function useLoad<T>(fn: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const reload = useCallback(() => {
    setLoading(true);
    setError(null);
    fn().then(setData).catch((e) => setError(e instanceof TelegramAppError ? e.message : 'Something went wrong.'))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(reload, [reload]);
  return { data, error, loading, reload };
}

function Card({ children }: { children: ReactNode }) {
  return <div className="rounded-xl bg-[var(--tg-section-bg)] p-4">{children}</div>;
}
function Status({ loading, error, onRetry }: { loading: boolean; error: string | null; onRetry: () => void }) {
  if (loading) return <p className="p-2 text-sm text-[var(--tg-hint)]">Loading...</p>;
  if (error) {
    return (
      <div className="flex items-center gap-2 p-2 text-sm">
        <span className="text-[var(--tg-destructive)]">{error}</span>
        <Button size="sm" variant="outline" onClick={onRetry}>Retry</Button>
      </div>
    );
  }
  return null;
}
function Row({ title, sub, onClick }: { title: string; sub?: string; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className="w-full rounded-lg bg-[var(--tg-section-bg)] p-3 text-left">
      <div className="truncate text-sm font-medium">{title}</div>
      {sub ? <div className="truncate text-xs text-[var(--tg-hint)]">{sub}</div> : null}
    </button>
  );
}

export function HomeView({ open, goApprovals }: { open: (r: DocRef) => void; goApprovals: () => void }) {
  const profile = useLoad<TgMe>(fetchMe);
  const dg = useLoad<TgDigest>(fetchDigest);
  const ap = useLoad(fetchApprovals);
  const count = ap.data?.items.length ?? 0;
  return (
    <div className="space-y-3">
      <h1 className="text-xl font-semibold">
        {profile.data ? `Hello, ${profile.data.full_name}` : 'Hello'}
      </h1>
      <Status loading={profile.loading} error={profile.error} onRetry={profile.reload} />
      <Card>
        <div className="text-xs uppercase text-[var(--tg-hint)]">Digest</div>
        <Status loading={dg.loading} error={dg.error} onRetry={dg.reload} />
        {dg.data ? (
          <>
            <p className="mt-1 whitespace-pre-wrap break-words text-sm">{dg.data.text}</p>
            <p className="mt-2 text-xs text-[var(--tg-hint)]">{dg.data.actions_24h} actions in the last 24 hours</p>
          </>
        ) : null}
      </Card>
      <button type="button" className="w-full text-left" onClick={goApprovals}>
        <Card>
          <div className="text-xs uppercase text-[var(--tg-hint)]">Pending approvals</div>
          <div className="text-2xl font-semibold" data-testid="pending-count">{ap.loading ? '-' : count}</div>
        </Card>
      </button>
      {ap.data?.items.slice(0, 3).map((i) => (
        <Row key={`${i.doctype}/${i.name}`} title={i.name} sub={i.doctype} onClick={() => open(i)} />
      ))}
    </div>
  );
}

export function ApprovalsView({ open }: { open: (r: DocRef) => void }) {
  const { data, error, loading, reload } = useLoad(fetchApprovals);
  const items: TgApprovalItem[] = data?.items ?? [];
  return (
    <div className="space-y-2">
      <h1 className="text-xl font-semibold">Approvals</h1>
      <Status loading={loading} error={error} onRetry={reload} />
      {!loading && !error && items.length === 0 ? (
        <p className="text-sm text-[var(--tg-hint)]">Nothing waiting for you.</p>
      ) : null}
      {items.map((i) => (
        <Row key={`${i.doctype}/${i.name}`} title={i.name} sub={[i.doctype, i.state].filter(Boolean).join(' - ')} onClick={() => open(i)} />
      ))}
    </div>
  );
}

export function SearchView({ config, open }: { config: TgConfig | null; open: (r: DocRef) => void }) {
  const choices = doctypeChoices(config);
  const [doctype, setDoctype] = useState('');
  const [text, setText] = useState('');
  const [items, setItems] = useState<TgSearchItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const go = async () => {
    if (!doctype.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setItems((await runSearch(doctype.trim(), text.trim())).items);
    } catch (e) {
      setItems(null);
      setError(e instanceof TelegramAppError ? e.message : 'Something went wrong.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-2">
      <h1 className="text-xl font-semibold">Search</h1>
      <DoctypePicker choices={choices} value={doctype} onChange={setDoctype} />
      <Input
        aria-label="Search text"
        placeholder="Search"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') void go(); }}
      />
      <Button className="w-full" disabled={busy || !doctype.trim()} onClick={() => void go()}>Search</Button>
      {error ? <p className="text-sm text-[var(--tg-destructive)]">{error}</p> : null}
      {items && items.length === 0 ? <p className="text-sm text-[var(--tg-hint)]">No results.</p> : null}
      {items?.map((i) => (
        <Row key={i.name} title={i.title || i.name} sub={i.title && i.title !== i.name ? i.name : undefined} onClick={() => open({ doctype, name: i.name })} />
      ))}
    </div>
  );
}

export function DocView({ doc, onChanged }: { doc: DocRef; onChanged: () => void }) {
  const { data, error, loading, reload } = useLoad<TgDocSummary>(() => getDocSummary(doc.doctype, doc.name));
  return (
    <div className="space-y-3">
      <h1 className="break-words text-xl font-semibold">{data?.title || doc.name}</h1>
      <div className="text-xs text-[var(--tg-hint)]">
        {doc.doctype}{data?.workflow_state ? ` - ${data.workflow_state}` : data?.status ? ` - ${data.status}` : ''}
      </div>
      <Status loading={loading} error={error} onRetry={reload} />
      {data ? (
        <>
          <Card>
            <dl className="space-y-2">
              {data.fields.map((f) => (
                <div key={f.fieldname}>
                  <dt className="text-xs text-[var(--tg-hint)]">{f.label}</dt>
                  <dd className="whitespace-pre-wrap break-words text-sm">{formatFieldValue(f)}</dd>
                </div>
              ))}
            </dl>
          </Card>
          <ActionPanel
            doctype={doc.doctype}
            name={doc.name}
            actions={data.actions}
            onDone={() => { reload(); onChanged(); }}
          />
        </>
      ) : null}
    </div>
  );
}

export function ActivityView() {
  const { data, error, loading, reload } = useLoad<TgAudit>(() => fetchAudit(20));
  return (
    <div className="space-y-2">
      <h1 className="text-xl font-semibold">Activity</h1>
      <Status loading={loading} error={error} onRetry={reload} />
      {data ? <p className="text-xs text-[var(--tg-hint)]">{data.scope === 'all' ? 'All users' : 'Your activity'}</p> : null}
      {data?.items.map((i, idx) => (
        <Card key={`${i.creation}-${idx}`}>
          <div className="text-sm font-medium">{i.action} - {i.result}</div>
          <div className="text-xs text-[var(--tg-hint)] break-words">
            {[i.reference_doctype, i.reference_name].filter(Boolean).join(' ')} {i.frappe_user} {i.creation}
          </div>
        </Card>
      ))}
      {data && data.items.length === 0 ? <p className="text-sm text-[var(--tg-hint)]">No activity yet.</p> : null}
    </div>
  );
}

export function SettingsView({ roleScope, gateway, onSignedOut }: { roleScope: string; gateway: string; onSignedOut: () => void }) {
  const [busy, setBusy] = useState(false);
  return (
    <div className="space-y-3">
      <h1 className="text-xl font-semibold">Settings</h1>
      <Card>
        <div className="text-xs text-[var(--tg-hint)]">Role</div>
        <div className="text-sm">{roleScope}</div>
        <div className="mt-2 text-xs text-[var(--tg-hint)]">Gateway</div>
        <div className="text-sm break-words">{gateway}</div>
      </Card>
      <Button
        variant="destructive"
        className="w-full"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try { await revokeToken(); } catch { /* token is dropped locally regardless */ }
          onSignedOut();
        }}
      >
        Sign out
      </Button>
    </div>
  );
}
