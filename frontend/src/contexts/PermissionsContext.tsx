import { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { getMe, type MeResponse } from '@/services/permissionsApi';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PermissionsContextType {
  /** The user's Huf role name, or null if they have no role. */
  hufRole: string | null;
  /** Full flat list of capability strings the user has. */
  capabilities: string[];
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

const PermissionsContext = createContext<PermissionsContextType | undefined>(undefined);

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
    return data.capabilities.includes(capability);
  };

  return (
    <PermissionsContext.Provider
      value={{
        hufRole: data.huf_role,
        capabilities: data.capabilities,
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

export function usePermissions(): PermissionsContextType {
  const ctx = useContext(PermissionsContext);
  if (!ctx) {
    throw new Error('usePermissions must be used inside <PermissionsProvider>');
  }
  return ctx;
}
