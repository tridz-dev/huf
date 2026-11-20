import { Cloud, FileText, Globe, Type } from 'lucide-react';
import type { KnowledgeInputDoc } from '@/types/knowledge.types';
import { displayFileLabel } from './import/ingestionLabels';

/** Title shown for an input: its title, else file name, URL or the first 60 characters of text. */
export function inputTitle(input: KnowledgeInputDoc): string {
  if (input.title?.trim()) return input.title.trim();
  if (input.input_type === 'URL') return input.url || 'Web page';
  if (input.input_type === 'Text') return input.text?.trim().slice(0, 60) || 'Text';
  return displayFileLabel(input.file_name, input.external_key) || input.file || 'Untitled file';
}

/** Where the content came from, in plain words. */
export function inputOrigin(input: KnowledgeInputDoc): { label: string; icon: typeof FileText } {
  if (input.input_type === 'URL') return { label: input.url || 'Web page', icon: Globe };
  if (input.input_type === 'Text') return { label: 'Typed text', icon: Type };
  const key = input.external_key || '';
  if (key.startsWith('s3://')) return { label: key.replace(/#[0-9a-f]{40}$/, ''), icon: Cloud };
  return { label: 'Uploaded file', icon: FileText };
}
