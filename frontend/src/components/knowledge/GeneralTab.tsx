import { FormField, FormItem, FormLabel, FormControl, FormDescription, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Combobox } from '@/components/ui/combobox';
import { UseFormReturn } from 'react-hook-form';
import { useMemo } from 'react';
import { knowledgeTypes, knowledgeScopes, knowledgeStorageModes, vectorKnowledgeTypes } from '@/data/knowledge';
import type { KnowledgeSourceFormValues } from './types';

interface ProviderOption {
  name: string;
  provider_name?: string;
}

interface GeneralTabProps {
  form: UseFormReturn<KnowledgeSourceFormValues>;
  isNew: boolean;
  providers?: ProviderOption[];
}

export function GeneralTab({ form, isNew, providers = [] }: GeneralTabProps) {
  const watchKnowledgeType = form.watch('knowledge_type');
  const watchChromaMode = form.watch('chroma_mode');
  const watchPGVectorConnectionMode = form.watch('pgvector_connection_mode');
  const isVectorBackend = vectorKnowledgeTypes.includes(watchKnowledgeType as (typeof vectorKnowledgeTypes)[number]);

  const providerOptions = useMemo(
    () => providers.map((p) => ({ value: p.name, label: p.provider_name || p.name })),
    [providers],
  );

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

      {isVectorBackend && (
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
                    <Combobox
                      options={providerOptions}
                      value={field.value ?? ''}
                      onValueChange={field.onChange}
                      placeholder="Select AI Provider..."
                      searchPlaceholder="Search providers..."
                      emptyText="No providers found."
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

      {watchKnowledgeType === 'chroma' && (
        <Card>
          <CardHeader>
            <CardTitle>Chroma Connection Settings</CardTitle>
            <CardDescription>Use local persistent storage or connect to a Chroma server</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-6 sm:grid-cols-2">
            <FormField
              control={form.control}
              name="chroma_mode"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Chroma Mode</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value ?? 'File'}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Select mode" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value="File">File</SelectItem>
                      <SelectItem value="Server">Server</SelectItem>
                    </SelectContent>
                  </Select>
                  <FormDescription>File stores locally; Server connects to ChromaDB over HTTP</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            {watchChromaMode === 'Server' && (
              <>
                <FormField
                  control={form.control}
                  name="chroma_host"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Chroma Host</FormLabel>
                      <FormControl>
                        <Input placeholder="localhost" {...field} value={field.value ?? ''} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="chroma_port"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Chroma Port</FormLabel>
                      <FormControl>
                        <Input
                          type="number"
                          placeholder="8000"
                          {...field}
                          value={field.value ?? 8000}
                          onChange={(e) => field.onChange(e.target.value ? Number(e.target.value) : undefined)}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </>
            )}
          </CardContent>
        </Card>
      )}

      {watchKnowledgeType === 'pgvector' && (
        <Card>
          <CardHeader>
            <CardTitle>PGVector Connection Settings</CardTitle>
            <CardDescription>Connect HUF Knowledge to PostgreSQL with the pgvector extension</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-6 sm:grid-cols-2">
            <FormField
              control={form.control}
              name="pgvector_connection_mode"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Connection Mode</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value ?? 'External PostgreSQL'}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Select mode" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value="External PostgreSQL">External PostgreSQL</SelectItem>
                      <SelectItem value="Site PostgreSQL">Site PostgreSQL</SelectItem>
                    </SelectContent>
                  </Select>
                  <FormDescription>Use external PostgreSQL for MariaDB-backed Frappe sites</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="pgvector_table_name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Table Name</FormLabel>
                  <FormControl>
                    <Input placeholder="huf_knowledge_vectors" {...field} value={field.value ?? ''} />
                  </FormControl>
                  <FormDescription>PostgreSQL table used for vector chunks</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="pgvector_distance_metric"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Distance Metric</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value ?? 'cosine'}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Select metric" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value="cosine">Cosine</SelectItem>
                      <SelectItem value="l2">L2</SelectItem>
                      <SelectItem value="inner_product">Inner Product</SelectItem>
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="pgvector_index_type"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Index Type</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value ?? 'hnsw'}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Select index" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value="none">None</SelectItem>
                      <SelectItem value="hnsw">HNSW</SelectItem>
                      <SelectItem value="ivfflat">IVFFlat</SelectItem>
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />

            {watchPGVectorConnectionMode === 'External PostgreSQL' && (
              <>
                <FormField
                  control={form.control}
                  name="pgvector_host"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Host</FormLabel>
                      <FormControl>
                        <Input placeholder="localhost" {...field} value={field.value ?? ''} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="pgvector_port"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Port</FormLabel>
                      <FormControl>
                        <Input
                          type="number"
                          placeholder="5432"
                          {...field}
                          value={field.value ?? 5432}
                          onChange={(e) => field.onChange(e.target.value ? Number(e.target.value) : undefined)}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="pgvector_database"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Database</FormLabel>
                      <FormControl>
                        <Input placeholder="huf_vectors" {...field} value={field.value ?? ''} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="pgvector_user"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>User</FormLabel>
                      <FormControl>
                        <Input placeholder="postgres" {...field} value={field.value ?? ''} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="pgvector_password"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Password</FormLabel>
                      <FormControl>
                        <Input type="password" {...field} value={field.value ?? ''} />
                      </FormControl>
                      <FormDescription>Stored in Frappe as a Password field</FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="pgvector_sslmode"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>SSL Mode</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value ?? 'prefer'}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select SSL mode" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="prefer">Prefer</SelectItem>
                          <SelectItem value="require">Require</SelectItem>
                          <SelectItem value="disable">Disable</SelectItem>
                          <SelectItem value="allow">Allow</SelectItem>
                          <SelectItem value="verify-ca">Verify CA</SelectItem>
                          <SelectItem value="verify-full">Verify Full</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </>
            )}
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
