import { createContext, useContext, ReactNode } from 'react';

interface IntegrationsContextType {
  onAddProvider: () => void;
}

const IntegrationsContext = createContext<IntegrationsContextType | undefined>(undefined);

export function IntegrationsProvider({ children, onAddProvider }: { children: ReactNode; onAddProvider: () => void }) {
  return (
    <IntegrationsContext.Provider value={{ onAddProvider }}>
      {children}
    </IntegrationsContext.Provider>
  );
}

export function useIntegrations() {
  const context = useContext(IntegrationsContext);
  if (context === undefined) {
    throw new Error('useIntegrations must be used within an IntegrationsProvider');
  }
  return context;
}

