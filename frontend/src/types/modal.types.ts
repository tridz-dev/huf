export type ModalTab = 'explore' | 'ai-agents' | 'apps' | 'utility';

export interface TriggerOption {
  id: string;
  name: string;
  /** Short name for the step on the canvas and in its panel, when the card name is a sentence. */
  nodeTitle?: string;
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
  category: 'agent' | 'control' | 'people' | 'data' | 'apps' | 'advanced';
  /** Extra words that find this step in search (never shown). */
  keywords?: string[];
}
