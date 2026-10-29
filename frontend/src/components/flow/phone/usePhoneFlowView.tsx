import { useSyncExternalStore } from 'react';
import { ListTree, Map as MapIcon } from 'lucide-react';
import { DropdownMenuItem } from '@/components/ui/dropdown-menu';

/**
 * On a phone a flow opens as a read-only list of its steps; the map is one tap away. The header's "..." menu and the page
 * share this choice, so it lives outside both.
 */
export type PhoneFlowView = 'steps' | 'map';

let current: PhoneFlowView = 'steps';
const listeners = new Set<() => void>();

export function setPhoneFlowView(next: PhoneFlowView) {
  if (next === current) return;
  current = next;
  listeners.forEach((l) => l());
}

const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => listeners.delete(l);
};

export function usePhoneFlowView() {
  const view = useSyncExternalStore(subscribe, () => current, () => 'steps' as PhoneFlowView);
  const showingMap = view === 'map';
  const menuItem = (
    <DropdownMenuItem
      className="gap-2 min-h-11"
      data-testid="flow-phone-view-toggle-menu"
      onSelect={() => setPhoneFlowView(showingMap ? 'steps' : 'map')}
    >
      {showingMap ? <ListTree className="h-4 w-4" aria-hidden /> : <MapIcon className="h-4 w-4" aria-hidden />}
      {showingMap ? 'Show steps' : 'Show map'}
    </DropdownMenuItem>
  );
  return { view, setView: setPhoneFlowView, menuItem };
}
