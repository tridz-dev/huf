/** "Add provider" / "Add model" dialogs opened from the Setup tab's model picker. */
import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { createProvider, createModel } from '@/services/providerApi';

interface Props {
  mode: 'provider' | 'model' | null;
  onClose: () => void;
  provider: string;
  onProviderCreated: (name: string) => void | Promise<void>;
  onModelCreated: (name: string) => void | Promise<void>;
}

export function ProviderModelDialogs({ mode, onClose, provider, onProviderCreated, onModelCreated }: Props) {
  const [name, setName] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [busy, setBusy] = useState(false);
  const close = () => { setName(''); setApiKey(''); onClose(); };

  const create = async () => {
    if (!name.trim() || busy) return;
    setBusy(true);
    try {
      if (mode === 'provider') {
        const created = await createProvider({ provider_name: name.trim(), api_key: apiKey.trim() });
        await onProviderCreated(created.name);
        toast.success('Provider created');
      } else {
        const created = await createModel({ model_name: name.trim(), provider });
        await onModelCreated(created.name);
        toast.success('Model created');
      }
      close();
    } catch (error) {
      console.error(error);
      toast.error(`Failed to create ${mode}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={mode !== null} onOpenChange={(o) => { if (!o) close(); }}>
      <DialogContent>
        <DialogHeader><DialogTitle>{mode === 'provider' ? 'Add provider' : 'Add model'}</DialogTitle></DialogHeader>
        <div className="space-y-4">
          <Field label={mode === 'provider' ? 'Provider name' : 'Model name'} required>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder={mode === 'provider' ? 'OpenAI' : 'gpt-4o'} />
          </Field>
          {mode === 'provider' && (
            <Field label="API key">
              <Input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="API key" />
            </Field>
          )}
          <Button type="button" onClick={() => void create()} disabled={!name.trim() || busy || (mode === 'model' && !provider)}>
            {busy ? 'Creating...' : mode === 'provider' ? 'Create provider' : 'Create model'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
