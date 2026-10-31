import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import { INTEGRATION_GUIDES } from '@/data/integrationGuides';

interface IntegrationSetupGuideProps {
  service: string;
}

/** "How to connect" for Gmail, Slack, Google Sheets and Google Drive: closed by default so the credentials stay in view. */
export function IntegrationSetupGuide({ service }: IntegrationSetupGuideProps) {
  const guide = INTEGRATION_GUIDES[service];
  if (!guide) return null;
  return (
    <Accordion type="single" collapsible className="rounded-lg border bg-muted/30 px-4" data-testid="integration-setup-guide">
      <AccordionItem value="how" className="border-b-0">
        <AccordionTrigger className="py-3" data-testid="integration-setup-toggle">
          {guide.title}
        </AccordionTrigger>
        <AccordionContent className="space-y-3">
          <ol className="list-decimal space-y-1 pl-5 text-sm text-muted-foreground" data-testid="integration-setup-steps">
            {guide.steps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
          <p className="text-sm text-muted-foreground" data-testid="integration-setup-scopes">
            {guide.scopes}
          </p>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  );
}
