import type { ReactNode } from 'react';
import { useFormContext } from 'react-hook-form';
import { FormField, FormItem, FormLabel, FormControl, FormDescription, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { knowledgeTypes, knowledgeScopes } from '@/data/knowledge';
import type { KnowledgeSourceFormValues } from '../types';
import { AdvancedConfigFields } from '../AdvancedConfigFields';
import { isSmartSearch } from './createSourceHelpers';

type Name = keyof KnowledgeSourceFormValues;

function TextField({
  name,
  label,
  hint,
  type = 'text',
  className,
}: {
  name: Name;
  label: string;
  hint?: string;
  type?: 'text' | 'number' | 'password';
  className?: string;
}) {
  const { control } = useFormContext<KnowledgeSourceFormValues>();
  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem className={className}>
          <FormLabel>{label}</FormLabel>
          <FormControl>
            <Input
              type={type}
              {...field}
              value={(field.value as string | number | undefined) ?? ''}
              onChange={(e) =>
                field.onChange(type === 'number' ? (e.target.value === '' ? undefined : Number(e.target.value)) : e.target.value)
              }
            />
          </FormControl>
          {hint && <FormDescription>{hint}</FormDescription>}
          <FormMessage />
        </FormItem>
      )}
    />
  );
}

function SelectField({
  name,
  label,
  options,
  hint,
}: {
  name: Name;
  label: string;
  options: ReadonlyArray<{ label: string; value: string }>;
  hint?: ReactNode;
}) {
  const { control } = useFormContext<KnowledgeSourceFormValues>();
  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem>
          <FormLabel>{label}</FormLabel>
          <Select value={String(field.value ?? '')} onValueChange={field.onChange}>
            <FormControl>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
            </FormControl>
            <SelectContent>
              {options.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {hint && <FormDescription>{hint}</FormDescription>}
          <FormMessage />
        </FormItem>
      )}
    />
  );
}

/** Body of the "Advanced options" accordion. Technical terms are allowed here. */
export function CreateSourceAdvanced() {
  const { watch } = useFormContext<KnowledgeSourceFormValues>();
  const type = watch('knowledge_type');
  const chromaMode = watch('chroma_mode');
  const pgMode = watch('pgvector_connection_mode');
  const smart = isSmartSearch(type);

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <SelectField name="scope" label="Who can use it" options={knowledgeScopes} />
      <SelectField name="knowledge_type" label="Search backend" options={knowledgeTypes} />
      {smart && (
        <>
          <TextField name="embedding_model" label="Embedding model (LiteLLM id)" hint="e.g. openai/text-embedding-3-small" />
          <TextField name="vector_dimension" label="Vector dimension" type="number" hint="Must match the model output size" />
        </>
      )}
      <TextField name="chunk_size" label="Chunk size" type="number" />
      <TextField name="chunk_overlap" label="Chunk overlap" type="number" />
      {type === 'chroma' && (
        <>
          <SelectField
            name="chroma_mode"
            label="Chroma mode"
            options={[
              { label: 'File', value: 'File' },
              { label: 'Server', value: 'Server' },
            ]}
          />
          {chromaMode === 'Server' && (
            <>
              <TextField name="chroma_host" label="Chroma host" />
              <TextField name="chroma_port" label="Chroma port" type="number" />
            </>
          )}
        </>
      )}
      {type === 'pgvector' && (
        <>
          <SelectField
            name="pgvector_connection_mode"
            label="PostgreSQL connection"
            options={[
              { label: 'External PostgreSQL', value: 'External PostgreSQL' },
              { label: 'Site PostgreSQL', value: 'Site PostgreSQL' },
            ]}
          />
          <TextField name="pgvector_table_name" label="Table name" />
          {pgMode === 'External PostgreSQL' && (
            <>
              <TextField name="pgvector_host" label="Host" />
              <TextField name="pgvector_port" label="Port" type="number" />
              <TextField name="pgvector_database" label="Database" />
              <TextField name="pgvector_user" label="User" />
              <TextField name="pgvector_password" label="Password" type="password" />
            </>
          )}
        </>
      )}
      {type !== 'sqlite_fts' && (
        <div className="sm:col-span-2">
          <AdvancedConfigFields knowledgeType={type} />
        </div>
      )}
    </div>
  );
}
