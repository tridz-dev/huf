import { useCallback, useEffect, useState } from 'react';
import { Loader2, Users } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { listFlowMembers, removeFlowMember, type FlowMemberRow, type FlowMemberStatus } from '@/services/flow/steps/flowMembersApi';
import { formatAbsoluteTime } from '@/lib/serverTime';
import { DisabledReason } from '../DisabledReason';

const STATUS_WORD: Record<FlowMemberStatus, string> = { Active: 'Active', Waiting: 'Waiting', Completed: 'Finished', Exited: 'Left' };

/** The people who went through a flow: where each one is, and "Remove from this flow" to forget one. */
export function FlowMembersPanel({ flowId, open, onOpenChange, stepName }: { flowId: string; open: boolean; onOpenChange: (open: boolean) => void; stepName?: (nodeId: string) => string | undefined }) {
  const { canManage } = useFlowPermissions();
  const [rows, setRows] = useState<FlowMemberRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const [removing, setRemoving] = useState<FlowMemberRow | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setFailed(false);
    try {
      setRows(await listFlowMembers(flowId));
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, [flowId]);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  const confirmRemove = async () => {
    const row = removing;
    setRemoving(null);
    if (!row) return;
    try {
      await removeFlowMember(flowId, row.member_key);
    } catch {
      /* the reload below shows what is still there */
    }
    await load();
  };

  return (
    <>
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent side="right" className="flex w-full max-w-full flex-col gap-0 overflow-hidden p-0 sm:w-[min(640px,80vw)] sm:max-w-none" data-testid="flow-members">
          <SheetHeader className="shrink-0 border-b border-border px-6 pb-4 pt-6 pr-12">
            <SheetTitle className="flex items-center gap-2"><Users className="h-5 w-5 text-muted-foreground" aria-hidden /> People</SheetTitle>
            <SheetDescription>Everyone who has gone through this flow, and where they are now.</SheetDescription>
          </SheetHeader>
          <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5" data-testid="flow-members-body">
            {loading && rows.length === 0 ? (
              <div className="flex justify-center p-8"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" aria-label="Loading" /></div>
            ) : failed ? (
              <div className="space-y-2" role="alert" data-testid="flow-members-error">
                <p className="text-sm text-destructive">Could not load the people in this flow. Try again.</p>
                <Button type="button" size="sm" variant="outline" onClick={() => void load()}>Try again</Button>
              </div>
            ) : rows.length === 0 ? (
              <p className="text-sm text-muted-foreground" data-testid="flow-members-empty">No one has gone through this flow yet. People appear here once a chat or document starts a run.</p>
            ) : (
              <Table data-testid="flow-members-table">
                <TableHeader>
                  <TableRow>
                    <TableHead>Person</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Current step</TableHead>
                    <TableHead>Last activity</TableHead>
                    <TableHead><span className="sr-only">Actions</span></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((r) => (
                    <TableRow key={r.member_key} data-testid="flow-member-row">
                      <TableCell className="break-all">{r.member_key}</TableCell>
                      <TableCell>{STATUS_WORD[r.status] ?? r.status}</TableCell>
                      <TableCell>{(r.current_node_id && stepName?.(r.current_node_id)) || ''}</TableCell>
                      <TableCell>{formatAbsoluteTime(r.last_event_at)}</TableCell>
                      <TableCell>
                        <DisabledReason reason={canManage ? null : 'Only people who can edit this flow can remove people from it.'}>
                          <Button type="button" size="sm" variant="outline" aria-label={`Remove ${r.member_key} from this flow`} data-testid="flow-member-remove" onClick={() => setRemoving(r)}>
                            Remove from this flow
                          </Button>
                        </DisabledReason>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </div>
        </SheetContent>
      </Sheet>
      <AlertDialog open={removing !== null} onOpenChange={(o) => !o && setRemoving(null)}>
        <AlertDialogContent data-testid="flow-member-remove-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Remove {removing?.member_key} from this flow?</AlertDialogTitle>
            <AlertDialogDescription>This forgets what the flow saved for {removing?.member_key} and cancels their waiting run.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep them</AlertDialogCancel>
            <AlertDialogAction onClick={() => void confirmRemove()} data-testid="flow-member-remove-confirm">Remove</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
