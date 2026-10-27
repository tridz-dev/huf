// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { TemplatePreview } from './TemplatePreview';
import { parseWhatsAppFormat, type FormatNode } from './preview/whatsappFormat';
import type { PreviewModel } from './preview/previewModel';

const t = (value: string): FormatNode => ({ kind: 'text', value });

describe('parseWhatsAppFormat', () => {
  const cases: [string, string, FormatNode[]][] = [
    ['bold', '*hi*', [{ kind: 'bold', children: [t('hi')] }]],
    ['italic', 'a _b_ c', [t('a '), { kind: 'italic', children: [t('b')] }, t(' c')]],
    ['strike', '~x~', [{ kind: 'strike', children: [t('x')] }]],
    ['mono', '```a *b*```', [{ kind: 'mono', value: 'a *b*' }]],
    ['nesting', '*a _b_*', [{ kind: 'bold', children: [t('a '), { kind: 'italic', children: [t('b')] }] }]],
    ['unclosed', '*hi', [t('*hi')]],
    ['unclosed mono', '```hi', [t('```hi')]],
    ['spaced markers', '* hi *', [t('* hi *')]],
    ['escaped', '\\*hi\\*', [t('*hi*')]],
    ['snake_case untouched', 'snake_case_name', [t('snake_case_name')]],
    ['no span over newline', '*a\nb*', [t('*a\nb*')]],
  ];
  it.each(cases)('%s', (_n, src, expected) => {
    expect(parseWhatsAppFormat(src)).toEqual(expected);
  });
});

const base: PreviewModel = { header: null, body: 'Hello', buttons: [] };

describe('TemplatePreview', () => {
  it('renders formatting as elements and keeps html as text', () => {
    const { container } = render(
      <TemplatePreview time="10:00" model={{ ...base, body: '*bold* <script>alert(1)</script>\nline2 https://a.b' }} />,
    );
    expect(container.querySelector('strong')?.textContent).toBe('bold');
    expect(container.querySelector('script')).toBeNull();
    expect(container.textContent).toContain('<script>alert(1)</script>');
    expect(container.querySelector('a')).toBeNull();
    expect(screen.getByText('10:00')).toBeTruthy();
  });

  it('replaces numbered and named variables, else shows chips', () => {
    const { rerender } = render(<TemplatePreview model={{ ...base, body: 'Hi {{1}} {{first_name}}', samples: ['Ann'] }} />);
    expect(screen.getByText('{{first_name}}')).toBeTruthy();
    expect(screen.queryByText('{{1}}')).toBeNull();
    rerender(<TemplatePreview model={{ ...base, body: 'Hi {{first_name}}', samples: { first_name: 'Bo' } }} />);
    expect(screen.getByText(/Hi Bo/)).toBeTruthy();
  });

  it.each([
    [{ kind: 'image' }, 'header-image'],
    [{ kind: 'video' }, 'header-video'],
    [{ kind: 'document', filename: 'a.pdf' }, 'header-document'],
    [{ kind: 'location' }, 'header-location'],
  ] as const)('header %j', (header, id) => {
    render(<TemplatePreview model={{ ...base, header }} />);
    expect(screen.getByTestId(id)).toBeTruthy();
  });

  it('falls back when the sample image fails', () => {
    const { container } = render(<TemplatePreview model={{ ...base, header: { kind: 'image', url: 'x.png' } }} />);
    fireEvent.error(container.querySelector('img')!);
    expect(screen.getByTestId('header-image')).toBeTruthy();
  });

  it('collapses more than 3 buttons and expands in place', () => {
    const buttons = ['A', 'B', 'C', 'D'].map((text) => ({ type: 'QUICK_REPLY' as const, text }));
    render(<TemplatePreview model={{ ...base, buttons }} />);
    expect(screen.getAllByTestId('preview-button')).toHaveLength(2);
    fireEvent.click(screen.getByText('See all options'));
    expect(screen.getAllByTestId('preview-button')).toHaveLength(4);
  });

  it('shows 3 buttons without collapsing', () => {
    const buttons = ['A', 'B', 'C'].map((text) => ({ type: 'URL' as const, text }));
    render(<TemplatePreview model={{ ...base, buttons }} />);
    expect(screen.getAllByTestId('preview-button')).toHaveLength(3);
    expect(screen.queryByText('See all options')).toBeNull();
  });

  it('sets dir=auto on text blocks', () => {
    const { container } = render(<TemplatePreview model={{ ...base, body: 'مرحبا', footer: 'f' }} />);
    expect(container.querySelectorAll('p[dir="auto"]').length).toBe(2);
  });

  it('renders canned samples', () => {
    const { unmount } = render(<TemplatePreview sample="marketing_default" />);
    expect(screen.getByText('Shop now')).toBeTruthy();
    expect(screen.getByText('Copy code')).toBeTruthy();
    unmount();
    render(<TemplatePreview sample="utility_default" />);
    expect(screen.getByText('Track shipment')).toBeTruthy();
  });

  it('still works with the legacy input prop', () => {
    render(<TemplatePreview input={{ body: 'Hi {{1}}', samples: ['Zed'], buttons: [{ type: 'PHONE_NUMBER', text: 'Call' }] }} />);
    expect(screen.getByText(/Hi Zed/)).toBeTruthy();
    expect(screen.getByText('Call')).toBeTruthy();
  });
});
