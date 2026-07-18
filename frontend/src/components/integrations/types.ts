import { z } from 'zod';

export const recipientRowSchema = z.object({
  name: z.string().optional(),
  recipient_name: z.string().min(1, 'Recipient name is required'),
  recipient_id: z.string().min(1, 'Recipient ID is required'),
  user: z.string().optional(),
});

export const integrationFormSchema = z.object({
  service: z.string().min(1, 'Service is required'),
  is_active: z.boolean(),
  is_default: z.boolean(),
  credentialValues: z.record(z.string(), z.string()),
  recipients: z.array(recipientRowSchema),
  telegram_agent: z.string().optional(),
  telegram_auto_setup_webhook: z.boolean(),
});

export type IntegrationFormValues = z.infer<typeof integrationFormSchema>;
export type RecipientFormRow = z.infer<typeof recipientRowSchema>;
