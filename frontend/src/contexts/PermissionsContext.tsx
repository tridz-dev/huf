import { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { getMe, type MeResponse } from '@/services/permissionsApi';
import { PAGE_ACCESS_ANY } from '@/lib/permissions/pageAccess';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PermissionsContextType {
  /** The user's Huf role name, or null if they have no role. */
  hufRole: string | null;
  /** Full flat list of capability strings the user has. */
  capabilities: string[];
  /** Capabilities the Huf Role grants that the server would refuse (the user's Frappe roles cannot write flows). */
  withheldCapabilities: string[];
  /** True while the initial getMe() call is in flight. */
  isLoading: boolean;
  /** Return true if the user has the given capability string. */
  hasCapability: (capability: string) => boolean;
  /** Force a refresh (e.g. after admin changes someone's role). */
  refresh: () => Promise<void>;
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

export const PermissionsContext = createContext<PermissionsContextType | undefined>(undefined);

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

interface PermissionsProviderProps {
  children: ReactNode;
}

export function PermissionsProvider({ children }: PermissionsProviderProps) {
  const [data, setData] = useState<MeResponse>({
    user: '',
    full_name: '',
    huf_role: null,
    capabilities: [],
    withheld_capabilities: [],
  });
  const [isLoading, setIsLoading] = useState(true);

  const load = async () => {
    setIsLoading(true);
    try {
      const me = await getMe();
      setData(me);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const hasCapability = (capability: string): boolean => {
    // "*" asks whether the person has any Huf role at all.
    if (capability === PAGE_ACCESS_ANY) return data.capabilities.length > 0;
    return data.capabilities.includes(capability);
  };

  return (
    <PermissionsContext.Provider
      value={{
        hufRole: data.huf_role,
        capabilities: data.capabilities,
        withheldCapabilities: data.withheld_capabilities ?? [],
        isLoading,
        hasCapability,
        refresh: load,
      }}
    >
      {children}
    </PermissionsContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/** True for Huf Admins; false for everyone else, and outside a provider (so it is safe in tests and shared components). */
export function useIsHufAdmin(): boolean {
  return useContext(PermissionsContext)?.hufRole === 'Huf Admin';
}

export function usePermissions(): PermissionsContextType {
  const ctx = useContext(PermissionsContext);
  if (!ctx) {
    throw new Error('usePermissions must be used inside <PermissionsProvider>');
  }
  return ctx;
}
