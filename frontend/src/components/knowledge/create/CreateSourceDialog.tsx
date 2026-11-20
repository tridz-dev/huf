import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useForm, FormProvider } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Dialog, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import {
  DialogScrollBody,
  DialogScrollContent,
  DialogScrollFooter,
  DialogScrollHeader,
} from '@/components/ui/dialog-scroll';
import { Button } from '@/components/ui/button';
import { createKnowledgeSource } from '@/services/knowledgeApi';
import { linkKnowledgeToAgent } from '@/services/agentApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import type { KnowledgeSourceDoc } from '@/types/knowledge.types';
import { knowledgeSourceFormSchema, type KnowledgeSourceFormValues } from '../types';
import { CreateSourceStepName } from './CreateSourceStepName';
import { CreateStepper } from './CreateStepper';
import { AddContentDialog } from '../import/AddContentDialog';
import { CREATE_SOURCE_DEFAULTS, buildCreatePayload, isSmartSearch } from './createSourceHelpers';

interface CreateSourceDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Agent to link the new source to (from /knowledge/new?agent=<id>). */
  agent?: string | null;
  /** Which choice the Add content step opens on. */
  initialAddTab?: 'upload' | 'storage';
}

export function CreateSourceDialog({ open, onOpenChange, agent, initialAddTab }: CreateSourceDialogProps) {
  const navigate = useNavigate();
  const [created, setCreated] = useState<KnowledgeSourceDoc | null>(null);
  const [busy, setBusy] = useState(false);
  const [linked, setLinked] = useState<unknown>(null);

  const form = useForm<KnowledgeSourceFormValues>({
    resolver: zodResolver(knowledgeSourceFormSchema),
    defaultValues: CREATE_SOURCE_DEFAULTS,
    mode: 'onChange',
  });

  useEffect(() => {
    if (open) {
      form.reset(CREATE_SOURCE_DEFAULTS);
      setCreated(null);
      setLinked(null);
    }
  }, [open, form]);

  const values = form.watch();
  const firstError = Object.values(form.formState.errors).find((e) => e?.message)?.message as string | undefined;
  let blockReason: string | null = null;
  if (!values.source_name?.trim()) blockReason = 'Enter a name to continue';
  else if (firstError) blockReason = firstError;
  else if (isSmartSearch(values.knowledge_type) && !values.embedding_model?.trim())
    blockReason = 'Choose a model for smart search';

  const finish = () => {
    if (!created) return;
    onOpenChange(false);
    if (agent) {
      navigate(`/agents/${agent}#knowledge`, { state: { linkedKnowledge: linked, showTab: 'knowledge' }, replace: true });
    } else {
      navigate(`/knowledge/${encodeURIComponent(created.name)}`);
    }
  };

  const submit = form.handleSubmit(async (v) => {
    setBusy(true);
    try {
      const doc = await createKnowledgeSource(buildCreatePayload(v));
      if (agent) {
        try {
          setLinked(await linkKnowledgeToAgent(agent, doc.name));
          toast.success('Knowledge source created and linked to agent');
        } catch (e) {
          toast.error(getFrappeErrorMessage(e) || 'Created, but could not link it to the agent');
        }
      } else {
        toast.success('Knowledge source created');
      }
      setCreated(doc);
    } catch (e) {
      toast.error(getFrappeErrorMessage(e) || 'Could not create this knowledge source');
    } finally {
      setBusy(false);
    }
  });

  if (created) {
    return (
      <AddContentDialog
        open={open}
        onOpenChange={(o) => !o && finish()}
        knowledgeSource={created.name}
        sourceLabel={created.source_name || created.name}
        onStarted={finish}
        onInputAdded={finish}
        onSkip={finish}
        initialTab={initialAddTab}
        headerExtra={<CreateStepper step={2} />}
      />
    );
  }

  return (
    <Dialog open={open} onOpenChange={(o) => (busy ? undefined : onOpenChange(o))}>
      <DialogScrollContent className="max-w-xl">
        <DialogScrollHeader>
          <DialogTitle>New knowledge source</DialogTitle>
          <DialogDescription asChild>
            <div>
              <CreateStepper step={1} />
            </div>
          </DialogDescription>
        </DialogScrollHeader>
        <FormProvider {...form}>
          <form onSubmit={submit} className="contents">
            <DialogScrollBody className="py-2">
              <CreateSourceStepName />
            </DialogScrollBody>
            <DialogScrollFooter>
              {blockReason && <span className="mr-auto self-center text-sm text-steel">{blockReason}</span>}
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
                Cancel
              </Button>
              <Button type="submit" disabled={busy || !!blockReason}>
                {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Create and add content
              </Button>
            </DialogScrollFooter>
          </form>
        </FormProvider>
      </DialogScrollContent>
    </Dialog>
  );
}
