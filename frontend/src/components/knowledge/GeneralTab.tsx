import { FormField, FormItem, FormLabel, FormControl, FormDescription, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { UseFormReturn } from 'react-hook-form';
import { knowledgeTypes, knowledgeScopes, knowledgeStorageModes } from '@/data/knowledge';
import type { KnowledgeSourceFormValues } from './types';

interface GeneralTabProps {
  form: UseFormReturn<KnowledgeSourceFormValues>;
  isNew: boolean;
}

export function GeneralTab({ form, isNew }: GeneralTabProps) {
  const watchKnowledgeType = form.watch('knowledge_type');

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Configuration</CardTitle>
          <CardDescription>Basic settings for this knowledge source</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6">
          {isNew && (
            <FormField
              control={form.control}
              name="source_name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Source Name</FormLabel>
                  <FormControl>
                    <Input placeholder="my-knowledge-source" {...field} />
                  </FormControl>
                  <FormDescription>Unique identifier for this knowledge source</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
          )}

          <FormField
            control={form.control}
            name="description"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Description</FormLabel>
                <FormControl>
                  <Textarea
                    placeholder="What this knowledge source contains"
                    className="min-h-[80px] resize-y"
                    {...field}
                  />
                </FormControl>
                <FormDescription>Human-readable description of the knowledge source</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <div className="grid gap-6 sm:grid-cols-2">
            <FormField
              control={form.control}
              name="knowledge_type"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Knowledge Type</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Select type" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {knowledgeTypes.map((type) => (
                        <SelectItem key={type.value} value={type.value}>
                          {type.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormDescription>Backend used for indexing and retrieval</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="scope"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Scope</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Select scope" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {knowledgeScopes.map((scope) => (
                        <SelectItem key={scope.value} value={scope.value}>
                          {scope.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="storage_mode"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Storage Mode</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Select storage mode" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {knowledgeStorageModes.map((mode) => (
                        <SelectItem key={mode.value} value={mode.value}>
                          {mode.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />
          </div>
        </CardContent>
      </Card>

      {watchKnowledgeType === 'sqlite_vec' && (
        <Card>
          <CardHeader>
            <CardTitle>Vector Settings</CardTitle>
            <CardDescription>Configure embedding model for vector-based retrieval</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-6 sm:grid-cols-2">
            <FormField
              control={form.control}
              name="embedding_model"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Embedding Model</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="text-embedding-3-small"
                      {...field}
                      value={field.value ?? ''}
                    />
                  </FormControl>
                  <FormDescription>LiteLLM model id (e.g. text-embedding-3-small)</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="vector_dimension"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Vector Dimension</FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      placeholder="1536"
                      {...field}
                      value={field.value ?? 1536}
                      onChange={(e) => field.onChange(e.target.value ? Number(e.target.value) : undefined)}
                    />
                  </FormControl>
                  <FormDescription>Must match the embedding model dimension</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="embedding_provider"
              render={({ field }) => (
                <FormItem className="sm:col-span-2">
                  <FormLabel>Embedding Provider</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="AI Provider name for API key resolution"
                      {...field}
                      value={field.value ?? ''}
                    />
                  </FormControl>
                  <FormDescription>AI Provider used for API key resolution (optional)</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Chunking Settings</CardTitle>
          <CardDescription>Control how content is split into chunks for indexing</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6 sm:grid-cols-2">
          <FormField
            control={form.control}
            name="chunk_size"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Chunk Size</FormLabel>
                <FormControl>
                  <Input
                    type="number"
                    placeholder="512"
                    {...field}
                    onChange={(e) => field.onChange(e.target.value ? Number(e.target.value) : 512)}
                  />
                </FormControl>
                <FormDescription>Number of characters per chunk (minimum 100)</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="chunk_overlap"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Chunk Overlap</FormLabel>
                <FormControl>
                  <Input
                    type="number"
                    placeholder="50"
                    {...field}
                    onChange={(e) => field.onChange(e.target.value ? Number(e.target.value) : 50)}
                  />
                </FormControl>
                <FormDescription>Overlap between adjacent chunks</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        </CardContent>
      </Card>
    </div>
  );
}
