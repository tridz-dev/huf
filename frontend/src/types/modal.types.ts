export type ModalTab = 'explore' | 'ai-agents' | 'apps' | 'utility';

export interface TriggerOption {
  id: string;
  name: string;
  description?: string;
  icon?: string;
  category: 'popular' | 'highlight' | 'utility' | 'app';
  tab: ModalTab;
}

export interface ActionOption {
  id: string;
  name: string;
  description?: string;
  icon?: string;
  category: 'transform' | 'control' | 'utility' | 'integration';
}
