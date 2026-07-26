import { createContext, useContext, ReactNode } from 'react';

interface AiProvidersContextType {
  onAddProvider: () => void;
}

const AiProvidersContext = createContext<AiProvidersContextType | undefined>(undefined);

export function AiProvidersProvider({ children, onAddProvider }: { children: ReactNode; onAddProvider: () => void }) {
  return (
    <AiProvidersContext.Provider value={{ onAddProvider }}>
      {children}
    </AiProvidersContext.Provider>
  );
}

export function useAiProviders() {
  const context = useContext(AiProvidersContext);
  if (context === undefined) {
    throw new Error('useAiProviders must be used within an AiProvidersProvider');
  }
  return context;
}

