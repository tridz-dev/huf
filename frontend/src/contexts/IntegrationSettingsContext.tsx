import { createContext, useContext } from 'react';

interface IntegrationSettingsContextType {
  onAddIntegration: () => void;
}

export const IntegrationSettingsContext = createContext<IntegrationSettingsContextType | undefined>(
  undefined,
);

export function useIntegrationSettingsContext() {
  const context = useContext(IntegrationSettingsContext);
  if (!context) {
    throw new Error('useIntegrationSettingsContext must be used within IntegrationSettingsProvider');
  }
  return context;
}

interface IntegrationSettingsProviderProps {
  children: React.ReactNode;
  onAddIntegration: () => void;
}

export function IntegrationSettingsProvider({
  children,
  onAddIntegration,
}: IntegrationSettingsProviderProps) {
  return (
    <IntegrationSettingsContext.Provider value={{ onAddIntegration }}>
      {children}
    </IntegrationSettingsContext.Provider>
  );
}
