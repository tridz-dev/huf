import { createContext, useContext } from 'react';

interface IntegrationServicesContextType {
  onAddService: () => void;
}

export const IntegrationServicesContext = createContext<IntegrationServicesContextType | undefined>(
  undefined,
);

export function useIntegrationServicesContext() {
  const context = useContext(IntegrationServicesContext);
  if (!context) {
    throw new Error('useIntegrationServicesContext must be used within IntegrationServicesProvider');
  }
  return context;
}

interface IntegrationServicesProviderProps {
  children: React.ReactNode;
  onAddService: () => void;
}

export function IntegrationServicesProvider({
  children,
  onAddService,
}: IntegrationServicesProviderProps) {
  return (
    <IntegrationServicesContext.Provider value={{ onAddService }}>
      {children}
    </IntegrationServicesContext.Provider>
  );
}
