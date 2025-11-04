import { createContext, useContext, useState, useCallback, ReactNode } from 'react';
import { TriggerConfig, ActionConfig } from '../types/flow.types';

interface ModalContextType {
  isTriggerModalOpen: boolean;
  isActionModalOpen: boolean;
  currentNodeId: string | null;
  sourceNodeId: string | null;
  openTriggerModal: (nodeId: string) => void;
  closeTriggerModal: () => void;
  openActionModal: (sourceNodeId: string) => void;
  closeActionModal: () => void;
  saveTriggerConfig: (config: TriggerConfig) => void;
  saveActionConfig: (config: ActionConfig) => void;
}

const ModalContext = createContext<ModalContextType | undefined>(undefined);

export function ModalProvider({ children }: { children: ReactNode }) {
  const [isTriggerModalOpen, setIsTriggerModalOpen] = useState(false);
  const [isActionModalOpen, setIsActionModalOpen] = useState(false);
  const [currentNodeId, setCurrentNodeId] = useState<string | null>(null);
  const [sourceNodeId, setSourceNodeId] = useState<string | null>(null);
  const [onSaveTrigger, setOnSaveTrigger] = useState<((config: TriggerConfig) => void) | null>(null);
  const [onSaveAction, setOnSaveAction] = useState<((config: ActionConfig) => void) | null>(null);

  const openTriggerModal = useCallback((nodeId: string) => {
    setCurrentNodeId(nodeId);
    setIsTriggerModalOpen(true);
  }, []);

  const closeTriggerModal = useCallback(() => {
    setIsTriggerModalOpen(false);
    setCurrentNodeId(null);
    setOnSaveTrigger(null);
  }, []);

  const openActionModal = useCallback((srcNodeId: string) => {
    setSourceNodeId(srcNodeId);
    setIsActionModalOpen(true);
  }, []);

  const closeActionModal = useCallback(() => {
    setIsActionModalOpen(false);
    setSourceNodeId(null);
    setOnSaveAction(null);
  }, []);

  const saveTriggerConfig = useCallback((config: TriggerConfig) => {
    if (onSaveTrigger) {
      onSaveTrigger(config);
    }
  }, [onSaveTrigger]);

  const saveActionConfig = useCallback((config: ActionConfig) => {
    if (onSaveAction) {
      onSaveAction(config);
    }
  }, [onSaveAction]);

  const value: ModalContextType = {
    isTriggerModalOpen,
    isActionModalOpen,
    currentNodeId,
    sourceNodeId,
    openTriggerModal,
    closeTriggerModal,
    openActionModal,
    closeActionModal,
    saveTriggerConfig,
    saveActionConfig
  };

  return <ModalContext.Provider value={value}>{children}</ModalContext.Provider>;
}

export function useModalContext() {
  const context = useContext(ModalContext);
  if (context === undefined) {
    throw new Error('useModalContext must be used within a ModalProvider');
  }
  return context;
}
