import React from 'react';

interface IconProps extends React.SVGProps<SVGSVGElement> {
  size?: number;
  className?: string;
}

export function WhatsAppIcon({ size = 20, className = '', ...props }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      className={className}
      {...props}
    >
      <path
        d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.263-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.521.151-.172.2-.296.3-.495.099-.198.05-.372-.025-.521-.075-.148-.669-1.611-.916-2.206-.242-.579-.487-.501-.669-.51l-.57-.01c-.198 0-.52.074-.792.372s-1.04 1.016-1.04 2.479 1.065 2.876 1.213 3.074c.149.198 2.095 3.2 5.076 4.487.709.306 1.263.489 1.694.626.712.226 1.36.194 1.872.118.571-.085 1.758-.719 2.006-1.413.248-.695.248-1.29.173-1.414-.074-.124-.272-.198-.57-.347z"
        fill="#25D366"
      />
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M12 2C6.477 2 2 6.477 2 12c0 2.159.66 4.164 1.791 5.823L2 22l6.326-1.658C9.92 21.432 10.938 22 12 22c5.523 0 10-4.477 10-10S17.523 2 12 2zm0 2a8 8 0 018 8c0 4.418-3.582 8-8 8-1.127 0-2.197-.233-3.167-.655l-.364-.158-3.75.983.999-3.655-.173-.377A7.957 7.957 0 014 12c0-4.418 3.582-8 8-8z"
        fill="#25D366"
      />
    </svg>
  );
}

export function MessengerIcon({ size = 20, className = '', ...props }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      className={className}
      {...props}
    >
      <path
        d="M12 2C6.36 2 2 6.13 2 11.7c0 2.91 1.19 5.43 3.16 7.15V22l3.35-1.84c1.1.31 2.27.48 3.49.48 5.64 0 10-4.13 10-9.7S17.64 2 12 2zm1.09 13.09l-2.58-2.75-5.04 2.75 5.54-5.88 2.64 2.75 4.98-2.75-5.54 5.88z"
        fill="url(#messenger-grad)"
      />
      <defs>
        <linearGradient id="messenger-grad" x1="2" y1="2" x2="22" y2="22" gradientUnits="userSpaceOnUse">
          <stop stopColor="#0084FF" />
          <stop offset="0.5" stopColor="#A855F7" />
          <stop offset="1" stopColor="#FF5252" />
        </linearGradient>
      </defs>
    </svg>
  );
}

export function InstagramIcon({ size = 20, className = '', ...props }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      className={className}
      {...props}
    >
      <path
        d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 2.156 4.919 5.406.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 5.258-4.919 5.406-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-2.199-4.919-5.42-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-5.258 4.919-5.406 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z"
        fill="url(#insta-grad)"
      />
      <defs>
        <linearGradient id="insta-grad" x1="2" y1="22" x2="22" y2="2" gradientUnits="userSpaceOnUse">
          <stop stopColor="#FFC107" />
          <stop offset="0.3" stopColor="#F44336" />
          <stop offset="0.6" stopColor="#E91E63" />
          <stop offset="1" stopColor="#9C27B0" />
        </linearGradient>
      </defs>
    </svg>
  );
}

export function TelegramIcon({ size = 20, className = '', ...props }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      className={className}
      {...props}
    >
      <path
        d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4.64 6.8c-.15 1.58-.8 5.42-1.13 7.19-.14.75-.73 1-1 .01l-2.73-2.01-1.32 1.27c-.15.15-.27.28-.55.28l.2-2.8 5.1-4.6c.22-.2-.05-.34-.34-.2l-6.3 3.97-2.72-.85c-.59-.18-.6-.59.12-.87l10.63-4.1c.49-.18.92.11.74.81z"
        fill="#24A1DE"
      />
    </svg>
  );
}

export function SlackIcon({ size = 20, className = '', ...props }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      className={className}
      {...props}
    >
      <path d="M5.042 15.165a2.528 2.528 0 0 1-2.52 2.523A2.528 2.528 0 0 1 0 15.165a2.527 2.527 0 0 1 2.522-2.52h2.52v2.52zM6.313 15.165a2.527 2.527 0 0 1 2.521-2.52 2.527 2.527 0 0 1 2.521 2.52v6.313A2.528 2.528 0 0 1 8.834 24a2.528 2.528 0 0 1-2.521-2.522v-6.313zM8.834 5.042a2.528 2.528 0 0 1-2.521-2.52A2.528 2.528 0 0 1 8.834 0a2.528 2.528 0 0 1 2.521 2.522v2.52H8.834zM8.834 6.313a2.528 2.528 0 0 1 2.521 2.521 2.528 2.528 0 0 1-2.521 2.521H2.522A2.528 2.528 0 0 1 0 8.834a2.528 2.528 0 0 1 2.522-2.521h6.312zM18.956 8.834a2.528 2.528 0 0 1 2.522-2.521A2.528 2.528 0 0 1 24 8.834a2.528 2.528 0 0 1-2.522 2.521h-2.522V8.834zM17.688 8.834a2.528 2.528 0 0 1-2.523 2.521 2.527 2.527 0 0 1-2.52-2.521V2.522A2.527 2.527 0 0 1 15.165 0a2.528 2.528 0 0 1 2.523 2.522v6.312zM15.165 18.956a2.528 2.528 0 0 1 2.523 2.522A2.528 2.528 0 0 1 15.165 24a2.527 2.527 0 0 1-2.52-2.522v-2.52h2.52zM15.165 17.688a2.527 2.527 0 0 1-2.52-2.523 2.527 2.527 0 0 1 2.52-2.52h6.313A2.528 2.528 0 0 1 24 15.165a2.528 2.528 0 0 1-2.522 2.523h-6.313z" fill="#E01E5A"/>
    </svg>
  );
}

export function EmailIcon({ size = 20, className = '', ...props }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      className={className}
      {...props}
    >
      <rect x="2" y="4" width="20" height="16" rx="3" stroke="#64748B" strokeWidth="2" />
      <path d="M2 7l10 7 10-7" stroke="#64748B" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function getProviderBrandIcon(provider: string, size = 20) {
  switch (provider) {
    case 'WhatsApp':
      return <WhatsAppIcon size={size} />;
    case 'Messenger':
      return <MessengerIcon size={size} />;
    case 'Instagram':
      return <InstagramIcon size={size} />;
    case 'Telegram':
      return <TelegramIcon size={size} />;
    case 'Slack':
      return <SlackIcon size={size} />;
    case 'Email':
      return <EmailIcon size={size} />;
    default:
      return <WhatsAppIcon size={size} />;
  }
}
