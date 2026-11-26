// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { AdvancedSettings } from './AdvancedSettings';

describe('AdvancedSettings', () => {
  it('is collapsed by default and toggles', () => {
    render(
      <AdvancedSettings>
        <input aria-label="hidden-field" />
      </AdvancedSettings>
    );
    expect(screen.queryByLabelText('hidden-field')).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('Advanced settings'));
    expect(screen.getByLabelText('hidden-field')).toBeInTheDocument();
  });

  it('opens when a hidden field has an error', () => {
    const { rerender } = render(
      <AdvancedSettings hasError={false}>
        <input aria-label="hidden-field" />
      </AdvancedSettings>
    );
    expect(screen.queryByLabelText('hidden-field')).not.toBeInTheDocument();
    rerender(
      <AdvancedSettings hasError>
        <input aria-label="hidden-field" />
      </AdvancedSettings>
    );
    expect(screen.getByLabelText('hidden-field')).toBeInTheDocument();
  });
});
