import { PageFrame } from '@/layouts/PageFrame';
import { labels } from '@/components/solutions/labels';

/** Placeholder; replaced by the New Solution wizard work package. */
export default function NewSolutionPage() {
  return (
    <PageFrame title={labels.newSolution}>
      <p className="text-sm text-steel">The setup wizard is coming soon.</p>
    </PageFrame>
  );
}
