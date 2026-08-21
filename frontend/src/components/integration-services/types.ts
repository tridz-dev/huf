import { z } from 'zod';
import { integrationCategories } from '@/data/integrations';

const credentialSchemaItemSchema = z.object({
  key: z
    .string()
    .min(1, 'Key is required')
    .regex(/^[a-z0-9_]+$/, 'Key must use lowercase letters, numbers, and underscores'),
  label: z.string().min(1, 'Label is required'),
  required: z.boolean().default(true),
  description: z.string().optional(),
});

export const integrationServiceFormSchema = z
  .object({
    service_name: z
      .string()
      .min(1, 'Service name is required')
      .regex(/^[a-z0-9_-]+$/, 'Service name must use lowercase letters, numbers, hyphens, and underscores'),
    category: z.enum(integrationCategories, { required_error: 'Category is required' }),
    description: z.string().optional(),
    documentation_url: z
      .string()
      .url('Must be a valid URL')
      .optional()
      .or(z.literal('')),
    required_credentials: z
      .array(credentialSchemaItemSchema)
      .min(1, 'At least one credential field is required')
      .refine(
        (items) => {
          const keys = items.map((item) => item.key);
          return new Set(keys).size === keys.length;
        },
        { message: 'Credential keys must be unique' },
      ),
  });

export type IntegrationServiceFormValues = z.infer<typeof integrationServiceFormSchema>;

export const defaultIntegrationServiceFormValues: IntegrationServiceFormValues = {
  service_name: '',
  category: 'Other',
  description: '',
  documentation_url: '',
  required_credentials: [
    {
      key: 'api_key',
      label: 'API key',
      required: true,
      description: '',
    },
  ],
};
