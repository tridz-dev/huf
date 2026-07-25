import type { LucideIcon } from 'lucide-react';
import {
  File,
  FileAudio,
  FileCode,
  FileImage,
  FileSpreadsheet,
  FileText,
  Presentation,
} from 'lucide-react';

export type FileTypeInfo = {
  label: string;
  extension: string;
  Icon: LucideIcon;
  isImage: boolean;
};

function getExtension(name: string): string {
  const parts = name.split('.');
  if (parts.length < 2) return '';
  return parts[parts.length - 1].toLowerCase();
}

export function getFileTypeInfo(file: File | string): FileTypeInfo {
  const name = typeof file === 'string' ? file : file.name;
  const mimeType = typeof file === 'string' ? undefined : file.type;
  const ext = getExtension(name);

  if (mimeType?.startsWith('image/') || ['png', 'jpg', 'jpeg', 'gif', 'webp'].includes(ext)) {
    return { label: 'Image', extension: ext || 'img', Icon: FileImage, isImage: true };
  }
  if (mimeType?.startsWith('audio/') || ['webm', 'mp3', 'wav', 'm4a', 'ogg', 'flac'].includes(ext)) {
    return { label: 'Audio', extension: ext || 'audio', Icon: FileAudio, isImage: false };
  }
  if (ext === 'pdf') {
    return { label: 'PDF', extension: ext, Icon: FileText, isImage: false };
  }
  if (ext === 'docx') {
    return { label: 'Word', extension: ext, Icon: FileText, isImage: false };
  }
  if (ext === 'xlsx') {
    return { label: 'Excel', extension: ext, Icon: FileSpreadsheet, isImage: false };
  }
  if (ext === 'pptx') {
    return { label: 'PowerPoint', extension: ext, Icon: Presentation, isImage: false };
  }
  if (ext === 'txt' || ext === 'md') {
    return { label: 'Text', extension: ext, Icon: FileText, isImage: false };
  }
  if (ext === 'csv') {
    return { label: 'CSV', extension: ext, Icon: FileCode, isImage: false };
  }
  if (ext === 'json') {
    return { label: 'JSON', extension: ext, Icon: FileCode, isImage: false };
  }
  if (ext === 'xml') {
    return { label: 'XML', extension: ext, Icon: FileCode, isImage: false };
  }
  if (ext === 'html' || ext === 'htm') {
    return { label: 'HTML', extension: ext, Icon: FileCode, isImage: false };
  }

  return { label: 'File', extension: ext || 'file', Icon: File, isImage: false };
}
