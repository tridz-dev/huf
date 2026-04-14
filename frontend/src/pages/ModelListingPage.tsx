import { useEffect, useMemo, useState } from 'react';
import { ArrowUpDown, Loader2, Pencil } from 'lucide-react';
import {
  ColumnDef,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  SortingState,
  useReactTable,
} from '@tanstack/react-table';
import { toast } from 'sonner';

import { FilterBar, LoadMoreButton, PageLayout } from '@/components/dashboard';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { useInfiniteScroll } from '@/hooks/useInfiniteScroll';
import {
  createModel,
  getModalities,
  getModel,
  getModelsPaginated,
  getProviders,
  updateModel,
} from '@/services/providerApi';
import type { AIModel, AIProvider } from '@/types/agent.types';
import type { ModalityOption } from '@/services/providerApi';


interface ModelListingPageProps {
  addModelKey?: number;
}

interface ModelFormData {
  model_name: string;
  provider: string;
  modalities: string | null;
}

const defaultModalityOptions: ModalityOption[] = [
  { label: 'Text', value: 'Text' },
  { label: 'Image', value: 'Image' },
  { label: 'Text-to-Speech', value: 'Text-to-Speech' },
  { label: 'Transcription', value: 'Transcription' },
  { label: 'Embeddings', value: 'Embeddings' },
];

const emptyFormData: ModelFormData = {
  model_name: '',
  provider: '',
  modalities: null,
};

export default function ModelListingPage({ addModelKey }: ModelListingPageProps) {
  const [providers, setProviders] = useState<AIProvider[]>([]);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [selectedModel, setSelectedModel] = useState<AIModel | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [loadingModelDetails, setLoadingModelDetails] = useState(false);
  const [loadingProviders, setLoadingProviders] = useState(true);
  const [saving, setSaving] = useState(false);
  const [sorting, setSorting] = useState<SortingState>([]);
  const [modalityOptions, setModalityOptions] = useState<ModalityOption[]>(defaultModalityOptions);
  const [loadingModalities, setLoadingModalities] = useState(false);
  const [formData, setFormData] = useState<ModelFormData>(emptyFormData);

  const {
    items: models,
    hasMore,
    initialLoading,
    loadingMore,
    search,
    setSearch,
    loadMore,
    total,
    reset,
    error,
  } = useInfiniteScroll<
    { page?: number; limit?: number; start?: number; search?: string },
    AIModel
  >({
    fetchFn: async (params) => {
      const response = await getModelsPaginated({
        page: params.page,
        limit: params.limit,
        start: params.start,
        search: params.search,
      });

      if (Array.isArray(response)) {
        return {
          data: response,
          hasMore: false,
          total: response.length,
        };
      }

      return {
        data: response.items,
        hasMore: response.hasMore,
        total: response.total,
      };
    },
    initialParams: {},
    pageSize: 10,
    debounceMs: 300,
    autoLoad: true,
  });

  useEffect(() => {
    if (!error) return;

    toast.error('Failed to load models', {
      description: error.message || 'An error occurred while fetching models. Please try again.',
      duration: 5000,
    });
  }, [error]);

  useEffect(() => {
    async function loadModalities() {
      setLoadingModalities(true);
      try {
        const options = await getModalities();
        if (options.length > 0) {
          setModalityOptions(options);
        }
      } catch (modalitiesError) {
        console.error('Error loading modality options:', modalitiesError);
        toast.error('Failed to load modality options');
      } finally {
        setLoadingModalities(false);
      }
    }

    loadModalities();
  }, []);

  useEffect(() => {
    async function loadProviders() {
      setLoadingProviders(true);
      try {
        const response = await getProviders();
        setProviders(Array.isArray(response) ? response : response.items);
      } catch (providerError) {
        console.error('Error fetching providers:', providerError);
        toast.error('Failed to load providers', {
          description: 'The provider list could not be loaded for the model form.',
          duration: 5000,
        });
        setProviders([]);
      } finally {
        setLoadingProviders(false);
      }
    }

    loadProviders();
  }, []);

  const openCreateDialog = () => {
    setSelectedModel(null);
    setIsEditing(false);
    setFormData(emptyFormData);
    setDialogOpen(true);
  };

  useEffect(() => {
    if (addModelKey && addModelKey > 0) {
      openCreateDialog();
    }
  }, [addModelKey]);

  const handleEdit = async (model: AIModel) => {
    setSelectedModel(model);
    setIsEditing(true);
    setDialogOpen(true);
    setLoadingModelDetails(true);

    try {
      const details = await getModel(model.name);
      setFormData({
        model_name: details.model_name || '',
        provider: details.provider || '',
        modalities: (() => {
          if (!details.modalities) {
            return null;
          }

          try {
            const parsed = JSON.parse(details.modalities);
            if (Array.isArray(parsed) && parsed.length > 0) {
              return String(parsed[0]);
            }
          } catch {
            // ignore
          }

          return details.modalities.split(',').map((m) => m.trim()).filter(Boolean)[0] || null;
        })(),
      });
    } catch (modelError) {
      console.error('Error loading model details:', modelError);
      toast.error('Failed to load model details');
    } finally {
      setLoadingModelDetails(false);
    }
  };

  const handleSave = async () => {
    if (!formData.model_name.trim()) {
      toast.error('Model name is required');
      return;
    }

    if (!formData.provider) {
      toast.error('Provider is required');
      return;
    }

    setSaving(true);
    try {
      const payload = {
        model_name: formData.model_name.trim(),
        provider: formData.provider,
        modalities: formData.modalities ? formData.modalities : null,
      };

      if (isEditing && selectedModel) {
        await updateModel(selectedModel.name, payload);
        toast.success('Model updated successfully');
      } else {
        await createModel(payload);
        toast.success('Model created successfully');
      }

      setDialogOpen(false);
      setSelectedModel(null);
      setIsEditing(false);
      setFormData(emptyFormData);
      await reset();
    } catch (saveError) {
      console.error('Error saving model:', saveError);
      toast.error(`Failed to ${isEditing ? 'update' : 'create'} model`);
    } finally {
      setSaving(false);
    }
  };

  const columns = useMemo<ColumnDef<AIModel>[]>(
    () => [
      {
        accessorKey: 'model_name',
        header: ({ column }) => (
          <Button
            variant="ghost"
            onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
            className="h-8 px-2"
          >
            Model Name
            <ArrowUpDown className="ml-2 h-4 w-4" />
          </Button>
        ),
        cell: ({ row }) => <div className="font-medium">{row.getValue('model_name')}</div>,
      },
      {
        accessorKey: 'provider',
        header: ({ column }) => (
          <Button
            variant="ghost"
            onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
            className="h-8 px-2"
          >
            Provider
            <ArrowUpDown className="ml-2 h-4 w-4" />
          </Button>
        ),
        cell: ({ row }) => (
          <div className="text-sm text-muted-foreground">{row.getValue('provider') || 'Unknown'}</div>
        ),
      },
      {
        accessorKey: 'modalities',
        header: 'Modalities',
        cell: ({ row }) => {
          const modalities = row.getValue('modalities') as string;
          if (!modalities) return null;
          try {
            const parsed = JSON.parse(modalities);
            return (
              <div className="flex flex-wrap gap-1">
                {parsed.map((m: string) => (
                  <Badge key={m} variant="secondary" className="text-[10px] py-0 px-1">
                    {m}
                  </Badge>
                ))}
              </div>
            );
          } catch {
            // Fallback for old format
            return (
              <div className="flex flex-wrap gap-1">
                {modalities.split(',').map((m) => (
                  <Badge key={m} variant="secondary" className="text-[10px] py-0 px-1">
                    {m.trim()}
                  </Badge>
                ))}
              </div>
            );
          }
        },
      },
      {
        id: 'actions',
        header: 'Actions',
        cell: ({ row }) => (
          <Button
            variant="outline"
            size="sm"
            className="gap-2"
            onClick={(event) => {
              event.stopPropagation();
              void handleEdit(row.original);
            }}
          >
            <Pencil className="h-4 w-4" />
            Edit
          </Button>
        ),
      },
    ],
    []
  );

  const table = useReactTable({
    data: models,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    onSortingChange: setSorting,
    state: {
      sorting,
    },
  });

  return (
    <PageLayout
      subtitle="Manage AI models and assign them to providers"
      filters={
        <FilterBar
          searchPlaceholder="Search models..."
          searchValue={search}
          onSearchChange={setSearch}
        />
      }
    >
      {error && !initialLoading && (
        <div className="text-center py-12">
          <p className="text-destructive mb-4">Failed to load models</p>
          <p className="text-sm text-muted-foreground mb-4">
            {error.message || 'An error occurred while fetching models.'}
          </p>
        </div>
      )}

      <div className="w-full">
        {initialLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="overflow-hidden rounded-md border">
            <Table>
              <TableHeader>
                {table.getHeaderGroups().map((headerGroup) => (
                  <TableRow key={headerGroup.id}>
                    {headerGroup.headers.map((header) => (
                      <TableHead key={header.id}>
                        {header.isPlaceholder
                          ? null
                          : flexRender(header.column.columnDef.header, header.getContext())}
                      </TableHead>
                    ))}
                  </TableRow>
                ))}
              </TableHeader>
              <TableBody>
                {table.getRowModel().rows?.length ? (
                  table.getRowModel().rows.map((row) => (
                    <TableRow
                      key={row.id}
                      className="cursor-pointer hover:bg-muted/50"
                      onClick={() => void handleEdit(row.original)}
                    >
                      {row.getVisibleCells().map((cell) => (
                        <TableCell key={cell.id}>
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={columns.length} className="h-24 text-center">
                      <div className="text-muted-foreground">No models found.</div>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      <LoadMoreButton
        hasMore={hasMore}
        loading={loadingMore}
        onLoadMore={loadMore}
        disabled={!!search || initialLoading}
      />

      {!hasMore && models.length > 0 && (
        <div className="text-center py-4 text-sm text-muted-foreground">
          {total !== undefined ? `Showing all ${total} models` : 'No more models to load'}
        </div>
      )}

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>{isEditing ? 'Edit Model' : 'Add Model'}</DialogTitle>
            <DialogDescription>
              {isEditing
                ? 'Update the model configuration and provider mapping.'
                : 'Create a new AI model and assign it to a provider.'}
            </DialogDescription>
          </DialogHeader>

          {loadingModelDetails ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="model_name">
                  Model Name <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="model_name"
                  placeholder="Enter model name"
                  value={formData.model_name}
                  onChange={(event) =>
                    setFormData((previous) => ({ ...previous, model_name: event.target.value }))
                  }
                />
              </div>

              <div className="space-y-2">
                <Label>
                  Provider <span className="text-destructive">*</span>
                </Label>
                <Select
                  value={formData.provider}
                  onValueChange={(value) => setFormData((previous) => ({ ...previous, provider: value }))}
                  disabled={loadingProviders}
                >
                  <SelectTrigger>
                    <SelectValue placeholder={loadingProviders ? 'Loading providers...' : 'Select provider'} />
                  </SelectTrigger>
                  <SelectContent>
                    {providers.map((provider) => (
                      <SelectItem key={provider.name} value={provider.name}>
                        {provider.provider_name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>Modality</Label>
                <Select
                  value={formData.modalities || ''}
                  onValueChange={(value) => setFormData((previous) => ({ ...previous, modalities: value || null }))}
                  disabled={loadingModalities}
                >
                  <SelectTrigger>
                    <SelectValue placeholder={loadingModalities ? 'Loading modalities...' : 'Select modality'} />
                  </SelectTrigger>
                  <SelectContent>
                    {modalityOptions.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDialogOpen(false)}
              disabled={saving || loadingModelDetails}
            >
              Cancel
            </Button>
            <Button onClick={() => void handleSave()} disabled={saving || loadingModelDetails}>
              {saving ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  {isEditing ? 'Saving...' : 'Creating...'}
                </>
              ) : isEditing ? (
                'Save'
              ) : (
                'Create'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageLayout>
  );
}
