import { useEffect, useState } from 'react';
import type { TgConfig } from '@/services/telegramAppApi';
import { getWebApp } from './telegramWebApp';
import { ActivityView, ApprovalsView, DocView, HomeView, SearchView, SettingsView, type DocRef } from './views';

type Tab = 'home' | 'approvals' | 'search' | 'activity' | 'settings';
const TABS: { id: Tab; label: string }[] = [
  { id: 'home', label: 'Home' },
  { id: 'approvals', label: 'Approvals' },
  { id: 'search', label: 'Search' },
  { id: 'activity', label: 'Activity' },
  { id: 'settings', label: 'Settings' },
];

interface Props {
  config: TgConfig | null;
  roleScope: string;
  gateway: string;
  onSignedOut: () => void;
}

export function TelegramApp({ config, roleScope, gateway, onSignedOut }: Props) {
  const [tab, setTab] = useState<Tab>('home');
  const [doc, setDoc] = useState<DocRef | null>(null);
  const [version, setVersion] = useState(0);

  // Telegram BackButton closes the document view.
  useEffect(() => {
    const back = getWebApp()?.BackButton;
    if (!back) return;
    if (!doc) { back.hide(); return; }
    const handler = () => setDoc(null);
    back.show();
    back.onClick(handler);
    return () => back.offClick(handler);
  }, [doc]);

  const features = config?.features;
  const tabs = TABS.filter((t) =>
    (t.id !== 'approvals' || features?.approvals !== false) && (t.id !== 'search' || features?.search !== false) &&
    (t.id !== 'activity' || features?.audit !== false));

  return (
    <div className="mx-auto flex min-h-screen max-w-xl flex-col">
      <main className="flex-1 p-4 pb-20" key={`${tab}-${version}-${doc?.doctype}-${doc?.name}`}>
        {doc ? (
          <DocView doc={doc} onChanged={() => setVersion((v) => v + 1)} />
        ) : tab === 'home' ? (
          <HomeView open={setDoc} goApprovals={() => setTab('approvals')} />
        ) : tab === 'approvals' ? (
          <ApprovalsView open={setDoc} />
        ) : tab === 'search' ? (
          <SearchView config={config} open={setDoc} />
        ) : tab === 'activity' ? (
          <ActivityView />
        ) : (
          <SettingsView roleScope={roleScope} gateway={gateway} onSignedOut={onSignedOut} />
        )}
      </main>
      <nav className="fixed inset-x-0 bottom-0 flex border-t bg-[var(--tg-secondary-bg)]" aria-label="Sections">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => { setDoc(null); setTab(t.id); }}
            aria-current={!doc && tab === t.id ? 'page' : undefined}
            className={`flex-1 py-3 text-xs ${!doc && tab === t.id ? 'font-semibold text-[var(--tg-button)]' : 'text-[var(--tg-hint)]'}`}
          >
            {t.label}
          </button>
        ))}
      </nav>
    </div>
  );
}
