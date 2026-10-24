import { useParams } from 'react-router-dom';
import { PageFrame } from '@/layouts/PageFrame';

/** Placeholder; replaced by the Solution detail work package. */
export default function SolutionDetailPage() {
  const { name } = useParams();
  return (
    <PageFrame title={name ?? 'Solution'}>
      <p className="text-sm text-steel">Solution details are coming soon.</p>
    </PageFrame>
  );
}
