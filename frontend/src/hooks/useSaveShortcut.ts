import { useEffect } from 'react';

interface UseSaveShortcutOptions {
  onSave: () => void | Promise<void>;
  enabled?: boolean;
  isSubmitting?: boolean;
  /** Allow save when a dialog is open (e.g. configure modal on listing pages). */
  allowInDialog?: boolean;
}

export function useSaveShortcut({
  onSave,
  enabled = true,
  isSubmitting = false,
  allowInDialog = false,
}: UseSaveShortcutOptions) {
  useEffect(() => {
    if (!enabled || isSubmitting) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (!(event.metaKey || event.ctrlKey) || event.key !== 's') return;

      const active = document.activeElement;
      if (active instanceof HTMLElement && active.isContentEditable) return;

      if (!allowInDialog && document.querySelector('[role=dialog][data-state=open]')) return;

      event.preventDefault();
      void onSave();
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onSave, enabled, isSubmitting, allowInDialog]);
}
