import { useState } from 'react';
import { Send, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Field, FieldRow, FieldAction } from '@/components/ui/field';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { call } from '@/lib/frappe-sdk';
import type { GatewayDoc } from '@/services/gatewayApi';

export function TestMessageSection({ gateway }: { gateway: GatewayDoc }) {
  const [testRecipientId, setTestRecipientId] = useState('');
  const [testSending, setTestSending] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);

  const handleTestSend = async () => {
    if (!testRecipientId.trim()) {
      toast.error('Enter a test recipient ID');
      return;
    }

    setTestSending(true);
    setTestResult(null);
    try {
      const result = await call.post('huf.ai.gateway_service.test_gateway_send', {
        gateway_name: gateway.name,
        test_recipient_id: testRecipientId.trim(),
      });

      setTestResult({
        success: result.success,
        message: result.message,
      });

      if (result.success) {
        toast.success(result.message || 'Test message sent');
      } else {
        toast.error(result.message);
      }
    } catch (error) {
      const errorMsg = getFrappeErrorMessage(error) || 'Failed to send test message';
      setTestResult({
        success: false,
        message: errorMsg,
      });
      toast.error(errorMsg);
    } finally {
      setTestSending(false);
    }
  };

  return (
    <div className="space-y-2 rounded-lg border p-4">
      <p className="text-sm font-medium">Test message</p>
      <p className="text-xs text-muted-foreground">
        {gateway.provider === 'WhatsApp'
          ? "Send a test to your own phone. If that number hasn't messaged this channel in the last 24 hours, WhatsApp only allows a template, so the fallback template (or Meta's hello_world) is sent instead."
          : 'Send a test message to check that this channel can deliver messages.'}
      </p>
      <FieldRow className="grid-cols-[1fr_auto]">
        <Field label={gateway.provider === 'WhatsApp' ? 'Phone number' : 'Recipient ID'} size="sm">
          <Input
            placeholder={
              gateway.provider === 'WhatsApp'
                ? 'With country code, e.g. 919876543210'
                : 'User, chat or channel ID'
            }
            value={testRecipientId}
            onChange={(e) => setTestRecipientId(e.target.value)}
            disabled={testSending}
          />
        </Field>
        <FieldAction>
          <Button
            type="button"
            variant="outline"
            onClick={handleTestSend}
            disabled={testSending || !testRecipientId.trim() || !gateway.is_enabled}
          >
            {testSending ? (
              <>
                <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> Sending
              </>
            ) : (
              <>
                <Send className="mr-1 h-3.5 w-3.5" /> Send
              </>
            )}
          </Button>
        </FieldAction>
      </FieldRow>
      {testResult && (
        <div
          className={`rounded text-xs p-2 ${
            testResult.success
              ? 'bg-success/10 text-success border border-success/30'
              : 'bg-destructive/10 text-destructive border border-destructive/30'
          }`}
        >
          {testResult.message}
        </div>
      )}
    </div>
  );
}
