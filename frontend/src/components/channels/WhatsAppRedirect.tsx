import { Navigate, useLocation } from 'react-router-dom';

/** Legacy `/whatsapp[/*]` entry: `?gateway=X` lands on that number's Home, otherwise the resolver. */
export function WhatsAppRedirect() {
  const gateway = new URLSearchParams(useLocation().search).get('gateway');
  const to = gateway
    ? `/channels/whatsapp/n/${encodeURIComponent(gateway)}/home`
    : '/channels/whatsapp';
  return <Navigate to={to} replace />;
}

export default WhatsAppRedirect;
