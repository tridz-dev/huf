import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react';
import { useNavigate, useParams, useBlocker, type Location } from 'react-router-dom';
import { toast } from 'sonner';
import { Save, Loader2, Settings2, Shield } from 'lucide-react';
import { usePermissions } from '@/contexts/PermissionsContext';
import { Button } from '@/components/ui/button';
import { TableBuilderCanvas } from '@/components/data-table/TableBuilderCanvas';
import { FieldConfigPanel } from '@/components/data-table/FieldConfigPanel';
import { TableSettingsPanel } from '@/components/data-table/TableSettingsPanel';
import { createDataTable, updateDataTable, getTableSchema, getTableDependencies } from '@/services/dataTableApi';
import { focusFirstError } from '@/components/builder';
import type { Dependent } from '@/components/grid';
import { builderReducer, initialBuilderState } from '@/components/data-table/builder/builderReducer';
import { FieldDeleteConfirm } from '@/components/data-table/builder/FieldDeleteConfirm';
import { isExistingField, needsDeleteConfirm, validateBuilder } from '@/components/data-table/builder/fieldRules';
import { LAYOUT_FIELD_TYPES } from '@/data/fieldTypes';
import type { DataTableFieldDef, DataTableFieldType } from '@/types/dataTable.types';
import { useIsMobile } from '@/hooks/use-mobile';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { UnsavedChangesDialog } from '@/components/UnsavedChangesDialog';
import { useSaveShortcut } from '@/hooks/useSaveShortcut';

export function DataTableBuilderPage() {
	const { tableId } = useParams<{ tableId: string }>();
	const navigate = useNavigate();
	const isEdit = !!tableId && tableId !== 'new';

	const { hasCapability, isLoading: permissionsLoading } = usePermissions();

	const [state, dispatch] = useReducer(builderReducer, initialBuilderState);
	const [saving, setSaving] = useState(false);
	const [loading, setLoading] = useState(isEdit);
	const isMobile = useIsMobile();
	const [isSidebarOpen, setIsSidebarOpen] = useState(false);
	const allowNavigationRef = useRef(false);
	const [showErrors, setShowErrors] = useState(false);
	const [pendingDelete, setPendingDelete] = useState<number | null>(null);
	const [deps, setDeps] = useState<{ recordCount?: number; dependents: Dependent[] }>({ dependents: [] });

	// Row count + agents/flows for the field-delete confirm. Best effort: no endpoint yet means no counts.
	useEffect(() => {
		if (!isEdit || !tableId) return;
		getTableDependencies(tableId)
			.then((d) =>
				setDeps({
					recordCount: d.record_count,
					dependents: [
						...d.agents.map((a) => ({ kind: 'Agent', label: a.agent_name || a.agent })),
						...d.flows.map((f) => ({ kind: 'Flow', label: f.title || f.name })),
					],
				})
			)
			.catch(() => setDeps({ dependents: [] }));
	}, [isEdit, tableId]);

	const errors = useMemo(
		() => (showErrors ? validateBuilder(state.tableName, state.fields) : null),
		[showErrors, state.tableName, state.fields]
	);
	const errorIndexes = useMemo(
		() => new Set(Object.keys(errors?.fields ?? {}).map(Number)),
		[errors]
	);

	const requestRemove = (index: number) => {
		const f = state.fields[index];
		if (f && needsDeleteConfirm(f, state.originalFields)) setPendingDelete(index);
		else dispatch({ type: 'REMOVE_FIELD', payload: index });
	};

	useEffect(() => {
		if (isEdit) {
			setLoading(true);
			getTableSchema(tableId)
				.then((schema) => {
					dispatch({ type: 'LOAD_SCHEMA', payload: schema });
				})
				.catch((err) => {
					toast.error('Failed to load table schema', {
						description: err.message,
					});
					navigate('/data');
				})
				.finally(() => setLoading(false));
		}
	}, [isEdit, tableId, navigate]);

	useEffect(() => {
		if (!state.isDirty) return;
		const handler = (e: BeforeUnloadEvent) => {
			e.preventDefault();
		};
		window.addEventListener('beforeunload', handler);
		return () => window.removeEventListener('beforeunload', handler);
	}, [state.isDirty]);

	const shouldBlock = useCallback(
		({ currentLocation, nextLocation }: { currentLocation: Location; nextLocation: Location }) => {
			if (allowNavigationRef.current) return false;
			if (!state.isDirty) return false;
			return (
				currentLocation.pathname !== nextLocation.pathname ||
				currentLocation.search !== nextLocation.search
			);
		},
		[state.isDirty]
	);

	const blocker = useBlocker(shouldBlock);

	const handleAddField = useCallback(
		(type: DataTableFieldType) => {
			const isLayout = LAYOUT_FIELD_TYPES.includes(type);
			// Frappe does not permit `in_list_view` on Attach/Attach Image fields.
			const supportsListView = type !== 'Attach' && type !== 'Attach Image';
			const baseName = isLayout
				? type.toLowerCase().replace(/\s+/g, '_')
				: 'new_field';
			const existingCount = state.fields.filter((f) =>
				f.fieldname.startsWith(baseName)
			).length;
			const fieldname =
				existingCount === 0 ? baseName : `${baseName}_${existingCount + 1}`;

			const newField: DataTableFieldDef = {
				fieldname,
				fieldtype: type,
				label: '',
				...(isLayout || !supportsListView ? {} : { in_list_view: state.fields.filter(
					(f) => !LAYOUT_FIELD_TYPES.includes(f.fieldtype)
				).length < 4 ? 1 : 0 as 0 | 1 }),
			};

			dispatch({ type: 'ADD_FIELD', payload: newField });
		},
		[state.fields]
	);

	const handleSave = async () => {
		const found = validateBuilder(state.tableName, state.fields);
		if (found.count > 0) {
			setShowErrors(true);
			if (found.tableName || found.noFields) dispatch({ type: 'SELECT_FIELD', payload: null });
			else if (found.firstFieldIndex !== null) dispatch({ type: 'SELECT_FIELD', payload: found.firstFieldIndex });
			// Wait for the panel to render the invalid control, then focus it.
			setTimeout(() => focusFirstError(), 0);
			return;
		}

		setSaving(true);
		try {
			if (isEdit) {
				await updateDataTable(state.registryName || tableId, {
					fields: state.fields,
					description: state.description,
					table_group: state.tableGroup,
					icon: state.icon,
				});
				toast.success('Table updated successfully');
				dispatch({ type: 'MARK_CLEAN' });
				allowNavigationRef.current = true;
				navigate(`/data/${state.registryName || tableId}`);
			} else {
				const result = await createDataTable({
					table_name: state.tableName.trim(),
					fields: state.fields,
					description: state.description,
					table_group: state.tableGroup,
					icon: state.icon,
					autoname_method: state.autonameMethod,
					title_field: state.titleField,
				});
				toast.success('Table created successfully');
				dispatch({ type: 'MARK_CLEAN' });
				allowNavigationRef.current = true;
				navigate(`/data/${result.name}`);
			}
		} catch (err) {
			toast.error(isEdit ? 'Failed to update table' : 'Failed to create table', {
				description: err instanceof Error ? err.message : 'An error occurred.',
			});
		} finally {
			setSaving(false);
		}
	};

	useSaveShortcut({
		onSave: handleSave,
		enabled: !loading,
		isSubmitting: saving,
	});

	if (!permissionsLoading && !hasCapability('data.tables.manage')) {
		return (
			<div className="flex items-center justify-center h-full">
				<div className="text-center max-w-md p-6">
					<Shield className="w-10 h-10 mx-auto text-muted-foreground mb-4" />
					<h2 className="text-lg font-semibold mb-2">Access Denied</h2>
					<p className="text-sm text-muted-foreground">
						You don't have permission to manage data tables.
					</p>
				</div>
			</div>
		);
	}

	if (loading) {
		return (
			<div className="flex items-center justify-center h-full">
				<Loader2 className="w-6 h-6 animate-spin text-steel-soft" />
			</div>
		);
	}

	const selectedField =
		state.selectedFieldIndex !== null ? state.fields[state.selectedFieldIndex] : null;

	const sidebarContent = (
		selectedField ? (
			<FieldConfigPanel
				key={state.selectedFieldIndex}
				field={selectedField}
				isExisting={isExistingField(selectedField, state.originalFields)}
				otherFieldnames={state.fields.filter((_, i) => i !== state.selectedFieldIndex).map((f) => f.fieldname)}
				errors={errors?.fields[state.selectedFieldIndex!]}
				onUpdate={(updates) =>
					dispatch({
						type: 'UPDATE_FIELD',
						payload: {
							index: state.selectedFieldIndex!,
							updates,
						},
					})
				}
				onDelete={() => requestRemove(state.selectedFieldIndex!)}
				onOpenTableSettings={() =>
					dispatch({ type: 'SELECT_FIELD', payload: null })
				}
			/>
		) : (
			<TableSettingsPanel
				tableName={state.tableName}
				description={state.description}
				tableGroup={state.tableGroup}
				icon={state.icon}
				autonameMethod={state.autonameMethod}
				titleField={state.titleField}
				fields={state.fields}
				isEdit={isEdit}
				tableNameError={errors?.tableName}
				onTableNameChange={(v) =>
					dispatch({ type: 'SET_TABLE_NAME', payload: v })
				}
				onDescriptionChange={(v) =>
					dispatch({ type: 'SET_DESCRIPTION', payload: v })
				}
				onTableGroupChange={(v) =>
					dispatch({ type: 'SET_TABLE_GROUP', payload: v })
				}
				onIconChange={(v) =>
					dispatch({ type: 'SET_ICON', payload: v })
				}
				onAutonameMethodChange={(v) =>
					dispatch({ type: 'SET_AUTONAME_METHOD', payload: v })
				}
				onTitleFieldChange={(v) =>
					dispatch({ type: 'SET_TITLE_FIELD', payload: v })
				}
			/>
		)
	);

	return (
		<div className="h-full flex flex-col">
			<div className="flex-1 flex overflow-hidden relative">
				{/* Left: Builder Canvas */}
				<div className="flex-1 overflow-y-auto p-6 bg-paper">
					<div className="max-w-2xl mx-auto rounded-lg border border-line bg-panel p-6">
						<TableBuilderCanvas
							fields={state.fields}
							selectedFieldIndex={state.selectedFieldIndex}
							onSelectField={(index) => {
								dispatch({ type: 'SELECT_FIELD', payload: index });
								if (isMobile) {
									setIsSidebarOpen(true);
								}
							}}
							onAddField={handleAddField}
							onRemoveField={requestRemove}
							errorIndexes={errorIndexes}
							emptyError={errors?.noFields}
							onReorderFields={(from, to) =>
								dispatch({
									type: 'REORDER_FIELDS',
									payload: { from, to },
								})
							}
						/>
					</div>
				</div>

				{/* Right: Config Panel */}
				{isMobile ? (
					<>
						<Button
							type="button"
							size="icon"
							variant="outline"
							className="fixed bottom-20 right-4 z-20 rounded bg-panel"
							onClick={() => setIsSidebarOpen(true)}
						>
							<Settings2 className="w-4 h-4" />
						</Button>
						<Sheet open={isSidebarOpen} onOpenChange={setIsSidebarOpen}>
							<SheetContent side="right" className="w-full sm:max-w-sm p-4 overflow-y-auto">
								<SheetHeader>
									<SheetTitle>
										{selectedField ? 'Field settings' : 'Table settings'}
									</SheetTitle>
								</SheetHeader>
								<div className="mt-4">
									{sidebarContent}
								</div>
							</SheetContent>
						</Sheet>
					</>
				) : (
					<div className="w-80 border-l border-line bg-panel overflow-y-auto p-4">
						{sidebarContent}
					</div>
				)}
			</div>

			{/* Bottom action bar */}
			<div className="border-t border-line px-6 py-4 flex items-center justify-between bg-panel/[.92] backdrop-blur-[12px]">
				{state.isDirty ? (
					<span className="text-xs text-steel-soft">Unsaved changes</span>
				) : (
					<span />
				)}
				<div className="flex items-center gap-2">
					<Button
						variant="outline"
						onClick={() => navigate(isEdit ? `/data/${tableId}` : '/data')}
					>
						Cancel
					</Button>
					<Button onClick={handleSave} disabled={saving}>
						{saving ? (
							<Loader2 className="w-4 h-4 mr-2 animate-spin" />
						) : (
							<Save className="w-4 h-4 mr-2" />
						)}
						{isEdit ? 'Save changes' : 'Create table'}
					</Button>
				</div>
			</div>

			<FieldDeleteConfirm
				open={pendingDelete !== null}
				onOpenChange={(o) => !o && setPendingDelete(null)}
				fieldLabel={pendingDelete !== null ? state.fields[pendingDelete]?.label ?? '' : ''}
				recordCount={deps.recordCount}
				dependents={deps.dependents}
				onConfirm={() => {
					if (pendingDelete !== null) dispatch({ type: 'REMOVE_FIELD', payload: pendingDelete });
					setPendingDelete(null);
				}}
			/>
			<UnsavedChangesDialog blocker={blocker} />
		</div>
	);
}
