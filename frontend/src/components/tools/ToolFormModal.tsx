import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../ui/tabs';
import { ToolTemplateCard } from './ToolTemplateCard';
import { ToolCreationForm } from './ToolCreationForm';
import { getToolTypes } from '@/services/toolApi';
import type { AgentToolType } from '@/types/agent.types';
import type { ToolTemplate, ToolFormData } from '@/types/toolTemplate.types';
import toolTemplatesConfig from '@/config/toolTemplates.json';

interface ToolFormModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode?: 'create' | 'edit';
  initialTemplate?: ToolTemplate | null;
  initialData?: Partial<ToolFormData> | null;
  onSubmit: (data: ToolFormData) => Promise<void>;
  loading?: boolean;
  toolName?: string; // Document name for edit mode (to fetch shared usage)
  currentAgentName?: string; // Current agent name to exclude from shared usage count
}

export function ToolFormModal({
  open,
  onOpenChange,
  mode = 'create',
  initialTemplate = null,
  initialData = null,
  onSubmit,
  loading = false,
  toolName,
  currentAgentName,
}: ToolFormModalProps) {
  const [toolTypes, setToolTypes] = useState<AgentToolType[]>([]);
  const [loadingTypes, setLoadingTypes] = useState(false);
  const [createView, setCreateView] = useState<'templates' | 'form'>(
    mode === 'edit' || initialTemplate ? 'form' : 'templates'
  );
  const [selectedTemplate, setSelectedTemplate] = useState<ToolTemplate | null>(
    initialTemplate
  );
  
  const templates = toolTemplatesConfig.templates as ToolTemplate[];

  // Determine which template to use for edit mode
  const getEditTemplate = (): ToolTemplate | null => {
    if (initialTemplate) return initialTemplate;
    if (!initialData?.types) return null;
    
    // Find template that contains this tool type
    return templates.find((t) => t.toolTypes.includes(initialData.types!)) || null;
  };

  // Load tool types when modal opens
  useEffect(() => {
    if (open) {
      setLoadingTypes(true);
      getToolTypes()
        .then((types) => {
          setToolTypes(types || []);
          setLoadingTypes(false);
        })
        .catch((error) => {
          console.error('Error loading tool types:', error);
          setLoadingTypes(false);
        });

      // Reset view state
      if (mode === 'edit') {
        setCreateView('form');
        const editTemplate = getEditTemplate();
        setSelectedTemplate(editTemplate);
      } else if (initialTemplate) {
        setCreateView('form');
        setSelectedTemplate(initialTemplate);
      } else {
        setCreateView('templates');
        setSelectedTemplate(null);
      }
    }
  }, [open, mode, initialTemplate, initialData]);

  const handleTemplateClick = (template: ToolTemplate) => {
    setSelectedTemplate(template);
    setCreateView('form');
  };

  const handleFormBack = () => {
    if (mode === 'edit') {
      // In edit mode, don't allow going back to templates
      onOpenChange(false);
    } else {
      setCreateView('templates');
      setSelectedTemplate(null);
    }
  };

  const handleFormSubmit = async (data: ToolFormData) => {
    await onSubmit(data);
  };

  const editTemplate = mode === 'edit' ? getEditTemplate() : null;
  const displayTemplate = selectedTemplate || editTemplate;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-5xl h-[80vh] flex flex-col p-0 overflow-hidden">
        <DialogHeader className="px-6 pt-6 pb-4 flex-shrink-0">
          <DialogTitle>{mode === 'edit' ? 'Edit Tool' : 'Add Tool'}</DialogTitle>
        </DialogHeader>

        {mode === 'create' && (
          <Tabs 
            value={createView === 'templates' ? 'templates' : 'form'} 
            onValueChange={(value) => {
              if (value === 'templates') {
                setCreateView('templates');
                setSelectedTemplate(null);
              }
            }}
            className="px-6 flex flex-col flex-1 min-h-0 overflow-hidden"
          >
            <TabsList className="grid w-full grid-cols-2 flex-shrink-0">
              <TabsTrigger value="templates">Templates</TabsTrigger>
              <TabsTrigger value="form" disabled={!selectedTemplate}>Form</TabsTrigger>
            </TabsList>

            <TabsContent 
              value="templates" 
              className="mt-4 data-[state=active]:flex data-[state=active]:flex-col data-[state=active]:flex-1 data-[state=active]:min-h-0 data-[state=active]:overflow-y-auto"
            >
              <div className="grid grid-cols-2 gap-4 max-w-4xl mx-auto pb-4">
                {templates.map((template) => (
                  <ToolTemplateCard
                    key={template.id}
                    template={template}
                    onClick={() => handleTemplateClick(template)}
                  />
                ))}
              </div>
            </TabsContent>

            <TabsContent 
              value="form" 
              className="mt-4 data-[state=active]:flex data-[state=active]:flex-col data-[state=active]:flex-1 data-[state=active]:min-h-0 data-[state=active]:overflow-y-auto data-[state=active]:overflow-x-hidden"
            >
              {displayTemplate && (
                <div className="pb-4 px-1">
                  <ToolCreationForm
                    template={displayTemplate}
                    toolTypes={toolTypes}
                    onSubmit={handleFormSubmit}
                    onBack={handleFormBack}
                    loading={loading || loadingTypes}
                    initialData={initialData}
                    mode={mode}
                    toolName={toolName}
                    currentAgentName={currentAgentName}
                  />
                </div>
              )}
            </TabsContent>
          </Tabs>
        )}

        {mode === 'edit' && displayTemplate && (
          <div className="px-6 flex flex-col flex-1 min-h-0 overflow-y-auto overflow-x-hidden">
            <div className="pb-4 px-1">
              <ToolCreationForm
                template={displayTemplate}
                toolTypes={toolTypes}
                onSubmit={handleFormSubmit}
                onBack={handleFormBack}
                loading={loading || loadingTypes}
                initialData={initialData}
                mode={mode}
                toolName={toolName}
                currentAgentName={currentAgentName}
              />
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
