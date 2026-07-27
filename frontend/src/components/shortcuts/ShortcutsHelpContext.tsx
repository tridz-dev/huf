import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';
import { useKeyboardShortcut } from '@/lib/shortcuts/useKeyboardShortcut';
import { KeyboardShortcutsDialog } from './KeyboardShortcutsDialog';

interface ShortcutsHelpContextValue {
  open: boolean;
  setOpen: (open: boolean) => void;
}

const ShortcutsHelpContext = createContext<ShortcutsHelpContextValue | null>(null);

/**
 * Owns the "?" keyboard shortcuts help dialog: binds the "?" key globally
 * and exposes `useShortcutsHelp()` so any visible affordance (sidebar
 * footer, help menu, etc.) can open the same dialog.
 */
export function ShortcutsHelpProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);

  useKeyboardShortcut({ key: '?' }, () => setOpen(true));

  const value = useMemo(() => ({ open, setOpen }), [open]);

  return (
    <ShortcutsHelpContext.Provider value={value}>
      {children}
      <KeyboardShortcutsDialog open={open} onOpenChange={setOpen} />
    </ShortcutsHelpContext.Provider>
  );
}

export function useShortcutsHelp(): ShortcutsHelpContextValue {
  const ctx = useContext(ShortcutsHelpContext);
  if (!ctx) {
    throw new Error('useShortcutsHelp must be used within a ShortcutsHelpProvider');
  }
  return ctx;
}
