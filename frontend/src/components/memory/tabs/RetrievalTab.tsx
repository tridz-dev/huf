import { UseFormReturn } from 'react-hook-form';
import {
  FormField,
  FormItem,
  FormLabel,
  FormControl,
  FormDescription,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { memoryInjectModes, type MemoryPolicyFormValues } from '../memoryPolicyFormSchema';

interface RetrievalTabProps {
  form: UseFormReturn<MemoryPolicyFormValues>;
}

export function RetrievalTab({ form }: RetrievalTabProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Retrieval</CardTitle>
        <CardDescription>
          Control how much memory is pulled back into the agent's context.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-6">
        <FormField
          control={form.control}
          name="inject_mode"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Inject mode</FormLabel>
              <Select value={field.value} onValueChange={field.onChange}>
                <FormControl>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {memoryInjectModes.map((mode) => (
                    <SelectItem key={mode} value={mode}>
                      {mode}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormDescription>
                <span className="block"><strong>Never</strong> — memory is never added to the prompt.</span>
                <span className="block"><strong>Relevant Only</strong> — only records relevant to the current turn are injected.</span>
                <span className="block"><strong>Always</strong> — every active memory record for the scope is injected on every turn.</span>
                <span className="block"><strong>Tool Only</strong> — memory is not auto-injected; the agent must call a memory tool to read it.</span>
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <div className="grid gap-6 sm:grid-cols-2">
          <FormField
            control={form.control}
            name="max_records"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Max records</FormLabel>
                <FormControl>
                  <Input
                    type="number"
                    min={0}
                    {...field}
                    onChange={(e) => field.onChange(Number(e.target.value))}
                  />
                </FormControl>
                <FormDescription>
                  Maximum number of memory records retrieved for a single turn.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="token_budget"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Token budget</FormLabel>
                <FormControl>
                  <Input
                    type="number"
                    min={0}
                    {...field}
                    onChange={(e) => field.onChange(Number(e.target.value))}
                  />
                </FormControl>
                <FormDescription>
                  Maximum tokens of memory content allowed into the prompt per turn.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>
      </CardContent>
    </Card>
  );
}
