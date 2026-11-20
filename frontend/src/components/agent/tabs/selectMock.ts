/**
 * Test helper: Radix Select's popper never settles under jsdom, so tests swap it for
 * a native stand-in. Use: vi.mock('@/components/ui/select', () => import('./selectMock').then((m) => m.selectMock()))
 */
import * as React from 'react';

type Ctx = { value?: string; onValueChange?: (v: string) => void; disabled?: boolean };
const C = React.createContext<Ctx>({});

export function selectMock() {
  return {
    Select: ({ value, onValueChange, disabled, children }: React.PropsWithChildren<Ctx>) =>
      React.createElement(C.Provider, { value: { value, onValueChange, disabled } }, React.createElement('div', null, children)),
    SelectTrigger: ({ children, ...rest }: React.PropsWithChildren<Record<string, unknown>>) => {
      const ctx = React.useContext(C);
      return React.createElement('button', { type: 'button', role: 'combobox', disabled: ctx.disabled, ...rest }, ctx.value ?? '', children);
    },
    SelectValue: () => null,
    SelectContent: ({ children }: React.PropsWithChildren) => React.createElement('div', { role: 'listbox' }, children),
    SelectItem: ({ value, children }: React.PropsWithChildren<{ value: string }>) => {
      const ctx = React.useContext(C);
      return React.createElement('button', { type: 'button', role: 'option', onClick: () => ctx.onValueChange?.(value) }, children);
    },
  };
}
