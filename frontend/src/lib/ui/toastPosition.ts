/** Where toasts appear: bottom right on a flow's canvas (clear of the overview map, bottom left), else the bottom centre; the top on a phone. */
export type ToastPosition = 'top-center' | 'bottom-center' | 'bottom-right';

export function toastPosition(pathname: string, isPhone: boolean): ToastPosition {
  if (isPhone) return 'top-center';
  return /^\/(?:huf\/)?flows\/[^/]+/.test(pathname) ? 'bottom-right' : 'bottom-center';
}
