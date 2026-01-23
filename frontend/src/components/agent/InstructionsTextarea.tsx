import { useState, useEffect } from 'react';
import { Expand, Sparkles } from 'lucide-react';
import { FormControl } from '@/components/ui/form';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '@/components/ui/dialog';
import { UseFormReturn, ControllerRenderProps } from 'react-hook-form';
import { cn } from '@/lib/utils';

interface InstructionsTextareaProps {
  // Form mode props
  form?: UseFormReturn<any>;
  field?: ControllerRenderProps<any, any>;
  
  // Standalone mode props
  value?: string;
  onChange?: (value: string) => void;
  
  // Common props
  placeholder?: string;
  className?: string;
  optimizingPrompt?: boolean;
  onOptimizePrompt?: () => void;
  showOptimize?: boolean;
  showExpand?: boolean;
  onExpand?: () => void;
  // Modal props
  modalTitle?: string;
  modalOpen?: boolean;
  onModalOpenChange?: (open: boolean) => void;
  // Internal prop to force standalone mode (used in modal)
  _isInModal?: boolean;
}

export function InstructionsTextarea({
  form,
  field,
  value: controlledValue,
  onChange: controlledOnChange,
  placeholder = "Define system prompt, goals, constraints...",
  className = "min-h-[300px] font-mono resize-y",
  optimizingPrompt = false,
  onOptimizePrompt,
  showOptimize = true,
  showExpand = true,
  onExpand,
  modalTitle = "Instructions",
  modalOpen: externalModalOpen,
  onModalOpenChange: externalOnModalOpenChange,
  _isInModal = false,
}: InstructionsTextareaProps) {
  const [internalModalOpen, setInternalModalOpen] = useState(false);
  const [modalValue, setModalValue] = useState('');

  // Determine if we're in form mode or standalone mode
  // Force standalone mode if we're inside the modal
  const isFormMode = !_isInModal && !!form && !!field;
  const isControlled = !isFormMode && controlledValue !== undefined;

  // Modal state management
  const isModalControlled = externalModalOpen !== undefined;
  const modalOpen = isModalControlled ? externalModalOpen : internalModalOpen;
  const setModalOpen = isModalControlled 
    ? (open: boolean) => externalOnModalOpenChange?.(open)
    : setInternalModalOpen;

  // Get current value
  const currentValue = isFormMode 
    ? field?.value || '' 
    : isControlled 
    ? controlledValue 
    : '';

  // Handle value changes
  const handleChange = (newValue: string) => {
    if (isFormMode && field) {
      field.onChange(newValue);
    } else if (isControlled && controlledOnChange) {
      controlledOnChange(newValue);
    }
  };

  // Handle expand (open modal)
  const handleExpand = () => {
    if (onExpand) {
      onExpand();
    } else {
      setModalValue(currentValue);
      setModalOpen(true);
    }
  };

  // Handle update from modal
  const handleUpdateFromModal = () => {
    handleChange(modalValue);
    setModalOpen(false);
  };

  // Sync modal value when modal opens
  useEffect(() => {
    if (modalOpen) {
      setModalValue(currentValue);
    }
  }, [modalOpen, currentValue]);

  // Textarea component
  const textareaElement = (
    <Textarea
      placeholder={placeholder}
      className={className}
      value={currentValue}
      onChange={(e) => handleChange(e.target.value)}
      disabled={isFormMode ? field?.disabled : false}
    />
  );
  
  return (
    <>
      <div className="relative">
        {isFormMode ? (
          <FormControl>
            {textareaElement}
          </FormControl>
        ) : (
          textareaElement
        )}
        
        {/* Action buttons */}
        <div className={cn("absolute right-4 flex gap-2",isFormMode ? "top-4" : "top-2")}>
          {showOptimize && onOptimizePrompt && (
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={onOptimizePrompt}
              disabled={optimizingPrompt}
            >
              <Sparkles className="w-4 h-4 mr-2" />
              {optimizingPrompt ? 'Optimizing...' : 'Optimize'}
            </Button>
          )}
        </div>
        
        {showExpand && !modalOpen && (
          <div className="absolute right-4 bottom-4 z-10">
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={handleExpand}
            >
              <Expand className="w-4 h-4" />
            </Button>
          </div>
        )}
      </div>

      {/* Modal */}
      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="max-w-[95vw] w-full min-w-[600px] max-h-[90vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>{modalTitle}</DialogTitle>
            <DialogDescription>Define system prompt, goals, and constraints</DialogDescription>
          </DialogHeader>
          <div className="flex-1 overflow-auto py-4 min-h-0">
            <InstructionsTextarea
              value={modalValue}
              onChange={setModalValue}
              placeholder={placeholder}
              className="min-h-[60vh] font-mono resize-y w-[calc(100%-2px)] mx-auto"
              optimizingPrompt={optimizingPrompt}
              onOptimizePrompt={onOptimizePrompt}
              showOptimize={showOptimize}
              showExpand={false}
              _isInModal={true}
            />
          </div>
          <DialogFooter>
            <Button type="button" onClick={handleUpdateFromModal}>
              Update
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
