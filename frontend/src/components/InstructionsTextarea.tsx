import { useState, useEffect } from 'react';
import { Expand } from 'lucide-react';
import { FormControl } from '@/components/ui/form';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '@/components/ui/dialog';
import { UseFormReturn, ControllerRenderProps, FieldValues } from 'react-hook-form';

interface InstructionsTextareaProps<TFieldValues extends FieldValues = FieldValues> {
  form?: UseFormReturn<TFieldValues>;
  field?: ControllerRenderProps<TFieldValues>;
  value?: string;
  onChange?: (value: string) => void;
  placeholder?: string;
  className?: string;
  showExpand?: boolean;
  onExpand?: () => void;
  disabled?: boolean;
  modalTitle?: string;
  modalDescription?: string;
  modalOpen?: boolean;
  onModalOpenChange?: (open: boolean) => void;
  _isInModal?: boolean;
}

export function InstructionsTextarea<TFieldValues extends FieldValues = FieldValues>({
  form,
  field,
  value: controlledValue,
  onChange: controlledOnChange,
  placeholder = 'Define system prompt, goals, constraints...',
  className = 'min-h-[300px] font-mono resize-y',
  showExpand = true,
  onExpand,
  disabled = false,
  modalTitle = 'Instructions',
  modalDescription = 'Define system prompt, goals, and constraints',
  modalOpen: externalModalOpen,
  onModalOpenChange: externalOnModalOpenChange,
  _isInModal = false,
}: InstructionsTextareaProps<TFieldValues>) {
  const [internalModalOpen, setInternalModalOpen] = useState(false);
  const [modalValue, setModalValue] = useState('');

  const isFormMode = !_isInModal && !!form && !!field;
  const isControlled = !isFormMode && controlledValue !== undefined;

  const isModalControlled = externalModalOpen !== undefined;
  const modalOpen = isModalControlled ? externalModalOpen : internalModalOpen;
  const setModalOpen = isModalControlled
    ? (open: boolean) => externalOnModalOpenChange?.(open)
    : setInternalModalOpen;

  const currentValue = isFormMode
    ? (field?.value as string | undefined) || ''
    : isControlled
      ? controlledValue
      : '';

  const handleChange = (newValue: string) => {
    if (isFormMode && field) {
      field.onChange(newValue);
    } else if (isControlled && controlledOnChange) {
      controlledOnChange(newValue);
    }
  };

  const handleExpand = () => {
    if (onExpand) {
      onExpand();
    } else {
      setModalValue(currentValue);
      setModalOpen(true);
    }
  };

  const handleUpdateFromModal = () => {
    handleChange(modalValue);
    setModalOpen(false);
  };

  useEffect(() => {
    if (modalOpen) {
      setModalValue(currentValue);
    }
  }, [modalOpen, currentValue]);

  const textareaElement = (
    <Textarea
      placeholder={placeholder}
      className={className}
      value={currentValue}
      onChange={(e) => handleChange(e.target.value)}
      disabled={disabled || (isFormMode ? field?.disabled : false)}
    />
  );

  return (
    <>
      <div className="relative">
        {isFormMode ? <FormControl>{textareaElement}</FormControl> : textareaElement}

        {showExpand && !modalOpen && (
          <div className="absolute right-4 bottom-4 z-10">
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={handleExpand}
              disabled={disabled}
            >
              <Expand className="w-4 h-4" />
            </Button>
          </div>
        )}
      </div>

      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="w-full min-w-0 max-h-[90vh] sm:max-w-[95vw] flex flex-col">
          <DialogHeader>
            <DialogTitle>{modalTitle}</DialogTitle>
            <DialogDescription>{modalDescription}</DialogDescription>
          </DialogHeader>
          <div className="flex-1 overflow-auto py-4 min-h-0">
            <InstructionsTextarea
              value={modalValue}
              onChange={setModalValue}
              placeholder={placeholder}
              className="min-h-[60vh] font-mono resize-y w-[calc(100%-2px)] mx-auto"
              showExpand={false}
              modalDescription={modalDescription}
              _isInModal
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
