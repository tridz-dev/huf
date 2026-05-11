import { createContext, useContext, ReactNode } from 'react';

interface ModelsContextType {
  onAddModel: () => void;
}

const ModelsContext = createContext<ModelsContextType | undefined>(undefined);

export function ModelsProvider({ children, onAddModel }: { children: ReactNode; onAddModel: () => void }) {
  return (
    <ModelsContext.Provider value={{ onAddModel }}>
      {children}
    </ModelsContext.Provider>
  );
}

export function useModels() {
  const context = useContext(ModelsContext);
  if (context === undefined) {
    throw new Error('useModels must be used within a ModelsProvider');
  }
  return context;
}
