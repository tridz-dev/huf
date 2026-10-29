import { useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { PageFrame } from '@/layouts/PageFrame';
import { TemplatesTab } from '@/components/whatsapp/TemplatesTab';
import { useChannelGateway } from '../useChannelGateway';

/** `templates/:name?` — the route param selects the template in the detail pane. */
export default function TemplatesSection() {
  const gateway = useChannelGateway();
  const { name } = useParams<{ name?: string }>();
  const navigate = useNavigate();
  const onSelect = useCallback(
    (next: string) => navigate(`${name ? '../' : ''}${encodeURIComponent(next)}`, { relative: 'path' }),
    [navigate, name],
  );
  return (
    <PageFrame title="Templates">
      <TemplatesTab gateway={gateway} selectedName={name ? decodeURIComponent(name) : ''} onSelect={onSelect} />
    </PageFrame>
  );
}
