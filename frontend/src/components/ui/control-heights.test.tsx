// @vitest-environment jsdom
//
// Control-height contract: every interactive primitive resolves to the same
// height token (h-control-sm/md/lg = 30/34/38px) for the same size, and none
// carries a hard-coded h-N / h-[Npx] utility.
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Select, SelectTrigger, SelectValue } from '@/components/ui/select';
import { InputGroup } from '@/components/ui/input-group';
import { Combobox } from '@/components/ui/combobox';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';

type Size = 'sm' | 'md' | 'lg';
const TOKEN: Record<Size, string> = {
  sm: 'h-control-sm',
  md: 'h-control-md',
  lg: 'h-control-lg',
};
const HARD_HEIGHT = /(^|\s)h-(\d+(\.\d+)?|\[[^\]]+\])(\s|$)/;
const heightTokens = (el: Element) =>
  el.className.split(/\s+/).filter((c) => /^h-control-(sm|md|lg)$/.test(c));

const options = [{ value: 'a', label: 'A' }];

function renderers(size: Size): Record<string, () => Element> {
  const legacy = size === 'md' ? 'default' : size;
  return {
    Input: () => render(<Input aria-label="x" size={legacy as 'default'} />).container.firstElementChild!,
    SelectTrigger: () => {
      render(
        <Select>
          <SelectTrigger aria-label="x" size={legacy as 'default'}>
            <SelectValue />
          </SelectTrigger>
        </Select>,
      );
      return screen.getByRole('combobox');
    },
    Button: () => render(<Button size={legacy as 'default'}>b</Button>).container.firstElementChild!,
    InputGroup: () => render(<InputGroup size={size} />).container.firstElementChild!,
    Combobox: () => {
      render(<Combobox options={options} size={legacy as 'default'} />);
      return screen.getByRole('combobox');
    },
    ToggleGroupItem: () => {
      render(
        <ToggleGroup type="single" size={legacy as 'default'}>
          <ToggleGroupItem value="a">a</ToggleGroupItem>
        </ToggleGroup>,
      );
      return screen.getByRole('radio');
    },
    TabsTrigger: () => {
      render(
        <Tabs defaultValue="a">
          <TabsList>
            <TabsTrigger value="a" size={size === 'sm' ? 'compact' : size === 'lg' ? 'lg' : 'default'}>
              a
            </TabsTrigger>
          </TabsList>
        </Tabs>,
      );
      return screen.getByRole('tab');
    },
  };
}

describe('control height contract', () => {
  const sizes: Size[] = ['sm', 'md', 'lg'];
  const names = Object.keys(renderers('md'));

  describe.each(sizes)('size %s', (size) => {
    it.each(names)('%s resolves to exactly %s token', (name) => {
      // Input/SelectTrigger gained `lg`; sm/md/lg all supported everywhere.
      const el = renderers(size)[name]();
      expect(heightTokens(el)).toEqual([TOKEN[size]]);
      expect(el.className).not.toMatch(HARD_HEIGHT);
    });
  });

  it('Button default text size matches Input (text-ui-text)', () => {
    const b = render(<Button>b</Button>).container.firstElementChild!;
    expect(b.className).toContain('text-ui-text');
    expect(b.className).not.toMatch(/(^|\s)text-sm(\s|$)/);
  });

  it('Button sm uses text-micro like Input sm', () => {
    const b = render(<Button size="sm">b</Button>).container.firstElementChild!;
    expect(b.className).toContain('text-micro');
  });

  it('Button icon sizes map to the md and sm tokens', () => {
    const a = render(<Button size="icon">i</Button>).container.firstElementChild!;
    const b = render(<Button size="icon-sm">i</Button>).container.firstElementChild!;
    expect(a.className).toContain('h-control-md');
    expect(b.className).toContain('h-control-sm');
  });

  it('Textarea min-height derives from a control token, not px', () => {
    const t = render(<Textarea aria-label="t" />).container.firstElementChild!;
    expect(t.className).toContain('min-h-[calc(var(--control-h-md)*2)]');
    expect(t.className).not.toMatch(/min-h-\[\d+px\]/);
  });

  it('InputGroup keeps h-auto for textarea groups', () => {
    const g = render(<InputGroup />).container.firstElementChild!;
    expect(g.className).toContain('has-[>textarea]:h-auto');
  });
});
