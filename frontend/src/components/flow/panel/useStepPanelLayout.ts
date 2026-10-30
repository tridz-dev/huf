import { useCallback, useLayoutEffect, useRef, useState, type RefObject } from 'react';
import { clampPanelWidth, defaultPanelWidth, panelLayout, readStoredPanelWidth, storePanelWidth } from '@/lib/ui/responsive';

/**
 * How wide the step panel is and whether it fits beside the canvas. `root` is the editor's box: its width is what the canvas
 * and the panel share. The width the person dragged to is remembered; the panel is narrowed (never below 300) before the canvas
 * drops under 520px, and below that it opens over the canvas instead. Also tells the toasts where the middle of the canvas is.
 */
export function useStepPanelLayout(root: RefObject<HTMLElement | null>, windowWidth: number) {
  const [available, setAvailable] = useState(windowWidth);
  const [wanted, setWanted] = useState<number>(() => readStoredPanelWidth() ?? defaultPanelWidth(windowWidth));
  const panelRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const el = root.current;
    if (!el) return;
    const measure = () => setAvailable(el.clientWidth);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [root]);

  const layout = panelLayout(available, wanted);
  const panelWidth = layout.mode === 'docked' ? layout.width : wanted;

  // No dependency list on purpose: the panel mounts after the flow has loaded, and its width must be set whenever it appears.
  useLayoutEffect(() => {
    if (panelRef.current) panelRef.current.style.width = `${panelWidth}px`;
    // Toasts are centred on the canvas, not on the window: shift them by half the difference of what sits left and right of it.
    const rootEl = root.current;
    const docked = layout.mode === 'docked' && !!panelRef.current && !!rootEl;
    const doc = document.documentElement;
    if (docked && rootEl) {
      doc.style.setProperty('--flow-toast-shift', `${Math.round((rootEl.getBoundingClientRect().left - panelWidth) / 2)}px`);
      doc.style.setProperty('--flow-toast-right', `${panelWidth + 16}px`);
    } else {
      doc.style.removeProperty('--flow-toast-shift');
      doc.style.removeProperty('--flow-toast-right');
    }
  });
  useLayoutEffect(() => () => { document.documentElement.style.removeProperty('--flow-toast-shift'); document.documentElement.style.removeProperty('--flow-toast-right'); }, []);

  const resize = useCallback((width: number) => setWanted(clampPanelWidth(width)), []);
  const commit = useCallback(() => setWanted((w) => { storePanelWidth(w); return w; }), []);

  return { mode: layout.mode, panelWidth, panelRef, resize, commit };
}
