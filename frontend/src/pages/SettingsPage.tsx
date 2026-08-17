import { useState } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { AgentSettingsTab } from '@/components/settings/AgentSettingsTab';
import { VoiceSettingsTab } from '@/components/settings/VoiceSettingsTab';
import { PageFrame } from '@/layouts/PageFrame';

export { SettingsPage };
export default SettingsPage;

const VALID_TABS = ['agent', 'voice'];

function SettingsPage() {
  const [activeTab, setActiveTab] = useState<string>(() => {
    const hashFromUrl = window.location.hash.slice(1);
    return VALID_TABS.includes(hashFromUrl) ? hashFromUrl : 'agent';
  });

  const handleTabChange = (value: string) => {
    setActiveTab(value);
    if (value === 'agent') {
      window.history.replaceState(null, '', window.location.pathname);
    } else {
      window.location.hash = value;
    }
  };

  return (
    <Tabs value={activeTab} onValueChange={handleTabChange}>
      <PageFrame
        title="Settings"
        meta="Defaults and provider configuration shared across agents"
        filters={
          <TabsList>
            <TabsTrigger value="agent">Agent defaults</TabsTrigger>
            <TabsTrigger value="voice">Voice / STT</TabsTrigger>
          </TabsList>
        }
      >
        <div className="max-w-4xl mx-auto">
          <TabsContent value="agent" className="mt-0">
            <AgentSettingsTab />
          </TabsContent>

          <TabsContent value="voice" className="mt-0">
            <VoiceSettingsTab />
          </TabsContent>
        </div>
      </PageFrame>
    </Tabs>
  );
}
