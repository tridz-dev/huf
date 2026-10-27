// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { useForm, FormProvider } from 'react-hook-form';

import { CredentialsTab } from './CredentialsTab';

const schema = [{ key: 'app_id', label: 'App ID', required: true, secret: false }] as never;

function Harness({ service, value }: { service: string; value: string }) {
  const form = useForm({ defaultValues: { service, credentialValues: { app_id: value } } as never });
  return (
    <FormProvider {...form}>
      <CredentialsTab form={form as never} schema={schema} isNew />
    </FormProvider>
  );
}

describe('CredentialsTab Teams hint', () => {
  it('shows the GUID hint once for a malformed Teams app id', () => {
    render(<Harness service="microsoft_teams" value="not-a-guid" />);
    expect(screen.getAllByText(/Expected a GUID/)).toHaveLength(1);
  });
  it('shows no hint for a valid GUID or another service', () => {
    const { unmount } = render(<Harness service="microsoft_teams" value="123e4567-e89b-12d3-a456-426614174000" />);
    expect(screen.queryByText(/Expected a GUID/)).toBeNull();
    unmount();
    render(<Harness service="telegram" value="not-a-guid" />);
    expect(screen.queryByText(/Expected a GUID/)).toBeNull();
  });
});
