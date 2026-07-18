import { useState } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { AgentSettingsTab } from '@/components/settings/AgentSettingsTab';
import { VoiceSettingsTab } from '@/components/settings/VoiceSettingsTab';

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
    <div className="h-full overflow-auto">
      <div className="p-6 max-w-4xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl font-semibold">Settings</h1>
          <p className="text-sm text-steel">
            Defaults and provider configuration shared across agents.
          </p>
        </div>

        <Tabs value={activeTab} onValueChange={handleTabChange}>
          <TabsList>
            <TabsTrigger value="agent">Agent Defaults</TabsTrigger>
            <TabsTrigger value="voice">Voice / STT</TabsTrigger>
          </TabsList>

          <TabsContent value="agent" className="mt-4">
            <AgentSettingsTab />
          </TabsContent>

          <TabsContent value="voice" className="mt-4">
            <VoiceSettingsTab />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
