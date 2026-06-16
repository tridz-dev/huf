import { useState } from 'react';
import { type HufAppManifest } from '@/services/appApi';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import AppCollectionView from './AppCollectionView';
import ChatWindow from '@/components/chat/ChatWindowV2';

interface Props { manifest: HufAppManifest }

export default function AppDashboardShell({ manifest }: Props) {
  const [activeTab, setActiveTab] = useState(manifest.nav[0]?.label ?? '');

  return (
    <div className="flex flex-col h-full p-4 gap-4">
      <h1 className="text-xl font-semibold">{manifest.label}</h1>
      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col">
        <TabsList>
          {manifest.nav.map(item => (
            <TabsTrigger key={item.label} value={item.label}>{item.label}</TabsTrigger>
          ))}
        </TabsList>
        {manifest.nav.map(item => (
          <TabsContent key={item.label} value={item.label} className="flex-1">
            {item.type === 'chat' ? (
              <ChatWindow chatId={null} defaultAgentName={manifest.agent.agent_name} />
            ) : (
              <AppCollectionView
                manifest={manifest}
                tableName={item.table!}
                layoutOverride={item.view}
                filterOverride={item.filter}
              />
            )}
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}
