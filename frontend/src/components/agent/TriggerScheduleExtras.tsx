import { Control } from 'react-hook-form';
import { Info } from 'lucide-react';
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

interface TriggerScheduleExtrasProps {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  control: Control<any>;
}

/**
 * Schedule-only extra rendered alongside interval/count in TriggerModal.
 * Lets a scheduled run pick "Instant" (today's Realtime default) or "Batch"
 * (queued, cheaper, results land later the same day). Mirrors how
 * TriggerDocEventExtras adds its own fields onto the shared control.
 */
export function TriggerScheduleExtras({ control }: TriggerScheduleExtrasProps) {
  return (
    <FormField
      control={control}
      name="execution_mode"
      render={({ field }) => (
        <FormItem>
          <div className="flex items-center gap-1.5">
            <FormLabel>Execution mode</FormLabel>
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    className="text-steel-soft hover:text-steel"
                    aria-label="What is execution mode?"
                  >
                    <Info className="h-3.5 w-3.5" />
                  </button>
                </TooltipTrigger>
                <TooltipContent className="max-w-xs text-xs">
                  Instant runs the moment it&apos;s due. Batch groups this run in with others and
                  delivers results later today, at a lower cost — a good fit when the result
                  isn&apos;t needed right away.
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
          <Select onValueChange={field.onChange} value={field.value || 'Realtime'}>
            <FormControl>
              <SelectTrigger>
                <SelectValue placeholder="Select execution mode" />
              </SelectTrigger>
            </FormControl>
            <SelectContent>
              <SelectItem value="Realtime">Instant</SelectItem>
              <SelectItem value="Batch">Batch — save ~50%, results by end of day</SelectItem>
            </SelectContent>
          </Select>
          <FormDescription>
            Batch runs later today instead of immediately, at a lower cost.
          </FormDescription>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}
