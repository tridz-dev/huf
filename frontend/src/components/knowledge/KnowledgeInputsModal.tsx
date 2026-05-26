import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import { Plus, Trash2, RefreshCw, FileText, Link, Type, Loader2, Upload } from 'lucide-react';
import { toast } from 'sonner';
import { knowledgeInputTypes } from '@/data/knowledge';
import type { KnowledgeInputDoc, KnowledgeInputType } from '@/types/knowledge.types';
import {
  getKnowledgeInputs,
  createKnowledgeInput,
  deleteKnowledgeInput,
  reprocessInput,
} from '@/services/knowledgeApi';
import { file as frappeFile } from '@/lib/frappe-sdk';

interface KnowledgeInputsModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  knowledgeSource: string;
  onSourceChanged: () => void;
}

function getInputStatusVariant(status: string): 'default' | 'secondary' | 'destructive' | 'outline' {
  switch (status) {
    case 'Indexed':
      return 'default';
    case 'Processing':
      return 'outline';
    case 'Error':
      return 'destructive';
    default:
      return 'secondary';
  }
}

function getInputIcon(type: KnowledgeInputType) {
  switch (type) {
    case 'File':
      return FileText;
    case 'URL':
      return Link;
    case 'Text':
      return Type;
  }
}

function getInputPreview(input: KnowledgeInputDoc): string {
  switch (input.input_type) {
    case 'File':
      return input.file_name || input.file || 'No file';
    case 'URL':
      return input.url || 'No URL';
    case 'Text':
      return input.text?.slice(0, 80) || 'No text';
    default:
      return '';
  }
}

export function KnowledgeInputsModal({
  open,
  onOpenChange,
  knowledgeSource,
  onSourceChanged,
}: KnowledgeInputsModalProps) {
  const [inputs, setInputs] = useState<KnowledgeInputDoc[]>([]);
  const [loading, setLoading] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);

  // Create form state
  const [inputType, setInputType] = useState<KnowledgeInputType>('File');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadedFileUrl, setUploadedFileUrl] = useState('');
  const [text, setText] = useState('');
  const [url, setUrl] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadInputs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getKnowledgeInputs(knowledgeSource);
      setInputs(data);
    } catch {
      toast.error('Failed to load knowledge inputs');
    } finally {
      setLoading(false);
    }
  }, [knowledgeSource]);

  useEffect(() => {
    if (open && knowledgeSource) {
      loadInputs();
    }
  }, [open, knowledgeSource, loadInputs]);

  const resetForm = () => {
    setInputType('File');
    setSelectedFile(null);
    setUploadedFileUrl('');
    setText('');
    setUrl('');
    setUploading(false);
    setUploadProgress(0);
    setShowCreate(false);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) {
      setSelectedFile(f);
      setUploadedFileUrl('');
    }
  };

  const handleUploadFile = async () => {
    if (!selectedFile) {
      toast.error('Please select a file first');
      return;
    }
    setUploading(true);
    setUploadProgress(0);
    try {
      const response = await frappeFile.uploadFile(
        selectedFile,
        {
          isPrivate: true,
          doctype: 'Knowledge Input',
        },
        (completed, total) => {
          if (total) setUploadProgress(Math.round((completed / total) * 100));
        },
      );
      const res = response as any;
      const fileUrl = res?.data?.message?.file_url;
      if (fileUrl) {
        setUploadedFileUrl(fileUrl);
        toast.success('File uploaded');
      } else {
        toast.error('Upload succeeded but no file URL returned');
      }
    } catch {
      toast.error('Failed to upload file');
    } finally {
      setUploading(false);
    }
  };

  const handleCreate = async () => {
    const data: Partial<KnowledgeInputDoc> = {
      knowledge_source: knowledgeSource,
      input_type: inputType,
    };

    if (inputType === 'File' && !uploadedFileUrl) {
      toast.error('Please upload a file first');
      return;
    }
    if (inputType === 'Text' && !text.trim()) {
      toast.error('Text content is required');
      return;
    }
    if (inputType === 'URL' && !url.trim()) {
      toast.error('URL is required');
      return;
    }

    if (inputType === 'File') data.file = uploadedFileUrl;
    if (inputType === 'Text') data.text = text;
    if (inputType === 'URL') data.url = url;

    setCreating(true);
    try {
      await createKnowledgeInput(data);
      toast.success('Knowledge input created');
      resetForm();
      await loadInputs();
      onSourceChanged();
    } catch {
      toast.error('Failed to create knowledge input');
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (name: string) => {
    try {
      await deleteKnowledgeInput(name);
      toast.success('Knowledge input deleted');
      await loadInputs();
      onSourceChanged();
    } catch {
      toast.error('Failed to delete knowledge input');
    }
  };

  const handleReprocess = async (name: string) => {
    try {
      await reprocessInput(name);
      toast.success('Reprocessing started');
      await loadInputs();
      onSourceChanged();
    } catch {
      toast.error('Failed to reprocess knowledge input');
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] flex flex-col">
        <DialogHeader className="flex-shrink-0">
          <DialogTitle>Knowledge Inputs</DialogTitle>
          <DialogDescription>
            Manage content inputs for this knowledge source
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto space-y-4 py-2">
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              {inputs.length} {inputs.length === 1 ? 'input' : 'inputs'}
            </p>
            <Button
              size="sm"
              variant={showCreate ? 'secondary' : 'default'}
              onClick={() => setShowCreate(!showCreate)}
            >
              <Plus className="w-4 h-4 mr-2" />
              New Input
            </Button>
          </div>

          {showCreate && (
            <div className="rounded-lg border p-4 space-y-4">
              <div className="space-y-2">
                <Label>Input Type</Label>
                <Select value={inputType} onValueChange={(v) => setInputType(v as KnowledgeInputType)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {knowledgeInputTypes.map((t) => (
                      <SelectItem key={t.value} value={t.value}>
                        {t.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {inputType === 'File' && (
                <div className="space-y-3">
                  <Label>File</Label>
                  <div className="flex items-center gap-2">
                    <Input
                      ref={fileInputRef}
                      type="file"
                      onChange={handleFileSelect}
                      className="flex-1"
                      disabled={uploading}
                    />
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={handleUploadFile}
                      disabled={!selectedFile || uploading || !!uploadedFileUrl}
                    >
                      {uploading ? (
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      ) : (
                        <Upload className="w-4 h-4 mr-2" />
                      )}
                      {uploading ? `${uploadProgress}%` : 'Upload'}
                    </Button>
                  </div>
                  {uploadedFileUrl && (
                    <p className="text-xs text-muted-foreground">
                      Uploaded: <span className="font-mono">{uploadedFileUrl}</span>
                    </p>
                  )}
                </div>
              )}

              {inputType === 'Text' && (
                <div className="space-y-2">
                  <Label>Text Content</Label>
                  <Textarea
                    placeholder="Paste text content here..."
                    className="min-h-[120px] resize-y"
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                  />
                </div>
              )}

              {inputType === 'URL' && (
                <div className="space-y-2">
                  <Label>URL</Label>
                  <Input
                    placeholder="https://example.com/docs"
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                  />
                </div>
              )}

              <div className="flex justify-end gap-2">
                <Button variant="outline" size="sm" onClick={resetForm}>
                  Cancel
                </Button>
                <Button
                  size="sm"
                  onClick={handleCreate}
                  disabled={creating || uploading || (inputType === 'File' && !uploadedFileUrl)}
                >
                  {creating && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                  Create
                </Button>
              </div>
            </div>
          )}

          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
            </div>
          ) : inputs.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground text-sm">
              No knowledge inputs yet. Add one to get started.
            </div>
          ) : (
            <div className="space-y-2">
              {inputs.map((input) => {
                const Icon = getInputIcon(input.input_type);
                return (
                  <div
                    key={input.name}
                    className="flex items-center gap-3 rounded-lg border p-3"
                  >
                    <Icon className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">
                        {getInputPreview(input)}
                      </p>
                      <div className="flex items-center gap-2 mt-1">
                        <Badge variant={getInputStatusVariant(input.status)} className="text-xs">
                          {input.status}
                        </Badge>
                        {input.chunks_created > 0 && (
                          <span className="text-xs text-muted-foreground">
                            {input.chunks_created} chunks
                          </span>
                        )}
                        {input.error_message && (
                          <span className="text-xs text-destructive truncate max-w-[200px]">
                            {input.error_message}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-1 flex-shrink-0">
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        onClick={() => handleReprocess(input.name)}
                        title="Reprocess"
                        disabled={input.status === 'Pending' || input.status === 'Processing'}
                      >
                        <RefreshCw className={`w-3.5 h-3.5 ${input.status === 'Processing' ? 'animate-spin' : ''}`} />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        onClick={() => handleDelete(input.name)}
                        title="Delete"
                        className="text-destructive hover:text-destructive"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
