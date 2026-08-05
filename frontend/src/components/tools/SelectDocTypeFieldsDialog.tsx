import { useEffect, useMemo, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { Dialog, DialogTitle } from '@/components/ui/dialog';
import {
  DialogScrollBody,
  DialogScrollContent,
  DialogScrollFooter,
  DialogScrollHeader,
} from '@/components/ui/dialog-scroll';
import { Button } from '@/components/ui/button';
import { MultiSelectCombobox } from '@/components/ui/multi-select-combobox';
import type { ParameterData } from './ParameterCard';
import {
  buildDocTypeFieldSelectOptions,
  buildParametersFromSelectedFields,
  loadDocTypeFieldCatalog,
  type DocTypeFieldCatalog,
} from './toolCreationForm.utils';

interface SelectDocTypeFieldsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  doctypeName: string;
  currentParameters: ParameterData[];
  onAddParameters: (rows: ParameterData[]) => void;
}

export function SelectDocTypeFieldsDialog({
  open,
  onOpenChange,
  doctypeName,
  currentParameters,
  onAddParameters,
}: SelectDocTypeFieldsDialogProps) {
  const [loading, setLoading] = useState(false);
  const [catalog, setCatalog] = useState<DocTypeFieldCatalog | null>(null);
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !doctypeName) {
      return;
    }

    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    setSelectedKeys([]);
    setCatalog(null);

    loadDocTypeFieldCatalog(doctypeName)
      .then((result) => {
        if (!cancelled) {
          setCatalog(result);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setLoadError('Failed to load DocType fields.');
          setCatalog(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [open, doctypeName]);

  const fieldOptions = useMemo(() => {
    if (!catalog) return [];

    return buildDocTypeFieldSelectOptions(
      catalog.parentMeta,
      catalog.childTableMetas,
      currentParameters
    ).map((option) => ({
      value: option.value,
      label: option.label,
      description: option.group,
    }));
  }, [catalog, currentParameters]);

  const handleAddFields = () => {
    if (!catalog || selectedKeys.length === 0) return;

    const newParams = buildParametersFromSelectedFields(
      selectedKeys,
      catalog.parentMeta,
      catalog.childTableMetas
    );

    if (newParams.length > 0) {
      onAddParameters(newParams);
    }

    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogScrollContent className="max-w-lg">
        <DialogScrollHeader>
          <DialogTitle>Select fields to add</DialogTitle>
        </DialogScrollHeader>

        <DialogScrollBody className="pb-6 space-y-4">
          {loading ? (
            <div className="flex items-center justify-center gap-2 py-8 text-sm text-steel">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading fields...
            </div>
          ) : loadError ? (
            <p className="text-sm text-destructive py-4">{loadError}</p>
          ) : fieldOptions.length === 0 ? (
            <p className="text-sm text-steel py-4">
              All available fields are already added.
            </p>
          ) : (
            <MultiSelectCombobox
              options={fieldOptions}
              values={selectedKeys}
              onValuesChange={setSelectedKeys}
              placeholder="Select fields..."
              searchPlaceholder="Search fields..."
              emptyText="No fields found."
              closeLabel="Close"
            />
          )}
        </DialogScrollBody>

        <DialogScrollFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            type="button"
            onClick={handleAddFields}
            disabled={loading || selectedKeys.length === 0 || fieldOptions.length === 0}
          >
            Add Fields
          </Button>
        </DialogScrollFooter>
      </DialogScrollContent>
    </Dialog>
  );
}
