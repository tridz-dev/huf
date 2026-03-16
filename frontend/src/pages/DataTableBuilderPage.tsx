import { useCallback, useEffect, useReducer, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Save, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { TableBuilderCanvas } from '@/components/data-table/TableBuilderCanvas';
import { FieldConfigPanel } from '@/components/data-table/FieldConfigPanel';
import { TableSettingsPanel } from '@/components/data-table/TableSettingsPanel';
import { createDataTable, updateDataTable, getTableSchema } from '@/services/dataTableApi';
import type { DataTableFieldDef, DataTableFieldType, DataTableSchema } from '@/types/dataTable.types';

interface BuilderState {
	tableName: string;
	description: string;
	icon: string;
	autonameMethod: string;
	titleField: string;
	fields: DataTableFieldDef[];
	selectedFieldIndex: number | null;
	isDirty: boolean;
	registryName: string;
}

type BuilderAction =
	| { type: 'SET_TABLE_NAME'; payload: string }
	| { type: 'SET_DESCRIPTION'; payload: string }
	| { type: 'SET_ICON'; payload: string }
	| { type: 'SET_AUTONAME_METHOD'; payload: string }
	| { type: 'SET_TITLE_FIELD'; payload: string }
	| { type: 'ADD_FIELD'; payload: DataTableFieldDef }
	| { type: 'UPDATE_FIELD'; payload: { index: number; updates: Partial<DataTableFieldDef> } }
	| { type: 'REMOVE_FIELD'; payload: number }
	| { type: 'REORDER_FIELDS'; payload: { from: number; to: number } }
	| { type: 'SELECT_FIELD'; payload: number | null }
	| { type: 'LOAD_SCHEMA'; payload: DataTableSchema };

const initialState: BuilderState = {
	tableName: '',
	description: '',
	icon: '',
	autonameMethod: 'Autoincrement',
	titleField: '',
	fields: [],
	selectedFieldIndex: null,
	isDirty: false,
	registryName: '',
};

function builderReducer(state: BuilderState, action: BuilderAction): BuilderState {
	switch (action.type) {
		case 'SET_TABLE_NAME':
			return { ...state, tableName: action.payload, isDirty: true };
		case 'SET_DESCRIPTION':
			return { ...state, description: action.payload, isDirty: true };
		case 'SET_ICON':
			return { ...state, icon: action.payload, isDirty: true };
		case 'SET_AUTONAME_METHOD':
			return { ...state, autonameMethod: action.payload, isDirty: true };
		case 'SET_TITLE_FIELD':
			return { ...state, titleField: action.payload, isDirty: true };
		case 'ADD_FIELD':
			return {
				...state,
				fields: [...state.fields, action.payload],
				selectedFieldIndex: state.fields.length,
				isDirty: true,
			};
		case 'UPDATE_FIELD': {
			const newFields = [...state.fields];
			newFields[action.payload.index] = {
				...newFields[action.payload.index],
				...action.payload.updates,
			};
			return { ...state, fields: newFields, isDirty: true };
		}
		case 'REMOVE_FIELD': {
			const newFields = state.fields.filter((_, i) => i !== action.payload);
			let newSelected = state.selectedFieldIndex;
			if (newSelected === action.payload) {
				newSelected = null;
			} else if (newSelected !== null && newSelected > action.payload) {
				newSelected--;
			}
			return {
				...state,
				fields: newFields,
				selectedFieldIndex: newSelected,
				isDirty: true,
			};
		}
		case 'REORDER_FIELDS': {
			const { from, to } = action.payload;
			const newFields = [...state.fields];
			const [moved] = newFields.splice(from, 1);
			newFields.splice(to, 0, moved);
			let newSelected = state.selectedFieldIndex;
			if (newSelected === from) {
				newSelected = to;
			} else if (newSelected !== null) {
				if (from < newSelected && to >= newSelected) newSelected--;
				else if (from > newSelected && to <= newSelected) newSelected++;
			}
			return { ...state, fields: newFields, selectedFieldIndex: newSelected, isDirty: true };
		}
		case 'SELECT_FIELD':
			return { ...state, selectedFieldIndex: action.payload };
		case 'LOAD_SCHEMA':
			return {
				...state,
				tableName: action.payload.table_name,
				description: action.payload.description || '',
				icon: action.payload.icon || '',
				autonameMethod: action.payload.autoname_method || 'Autoincrement',
				titleField: action.payload.title_field_name || '',
				fields: action.payload.fields,
				registryName: action.payload.name,
				selectedFieldIndex: null,
				isDirty: false,
			};
		default:
			return state;
	}
}

export function DataTableBuilderPage() {
	const { tableId } = useParams<{ tableId: string }>();
	const navigate = useNavigate();
	const isEdit = !!tableId && tableId !== 'new';

	const [state, dispatch] = useReducer(builderReducer, initialState);
	const [saving, setSaving] = useState(false);
	const [loading, setLoading] = useState(isEdit);

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

	const handleAddField = useCallback(
		(type: DataTableFieldType) => {
			const isLayout = type === 'Section Break' || type === 'Column Break';
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
				label: isLayout ? '' : '',
				...(isLayout ? {} : { in_list_view: state.fields.filter(
					(f) => f.fieldtype !== 'Section Break' && f.fieldtype !== 'Column Break'
				).length < 4 ? 1 : 0 as 0 | 1 }),
			};

			dispatch({ type: 'ADD_FIELD', payload: newField });
		},
		[state.fields]
	);

	const handleSave = async () => {
		if (!state.tableName.trim()) {
			toast.error('Table name is required');
			return;
		}

		const dataFields = state.fields.filter(
			(f) => f.fieldtype !== 'Section Break' && f.fieldtype !== 'Column Break'
		);
		if (dataFields.length === 0) {
			toast.error('Add at least one data field');
			return;
		}

		const unlabeledField = dataFields.find((f) => !f.label?.trim());
		if (unlabeledField) {
			toast.error('All fields must have a label');
			return;
		}

		setSaving(true);
		try {
			if (isEdit) {
				await updateDataTable(state.registryName || tableId, {
					fields: state.fields,
					description: state.description,
					icon: state.icon,
				});
				toast.success('Table updated successfully');
				navigate(`/data/${state.registryName || tableId}`);
			} else {
				const result = await createDataTable({
					table_name: state.tableName.trim(),
					fields: state.fields,
					description: state.description,
					icon: state.icon,
					autoname_method: state.autonameMethod,
					title_field: state.titleField,
				});
				toast.success('Table created successfully');
				navigate(`/data/${result.name}`);
			}
		} catch (err: any) {
			toast.error(isEdit ? 'Failed to update table' : 'Failed to create table', {
				description: err.message,
			});
		} finally {
			setSaving(false);
		}
	};

	if (loading) {
		return (
			<div className="flex items-center justify-center h-full">
				<Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
			</div>
		);
	}

	const selectedField =
		state.selectedFieldIndex !== null ? state.fields[state.selectedFieldIndex] : null;

	return (
		<div className="h-full flex flex-col">
			<div className="flex-1 flex overflow-hidden">
				{/* Left: Builder Canvas */}
				<div className="flex-1 overflow-y-auto p-6">
					<div className="max-w-2xl mx-auto">
						<TableBuilderCanvas
							fields={state.fields}
							selectedFieldIndex={state.selectedFieldIndex}
							onSelectField={(index) =>
								dispatch({ type: 'SELECT_FIELD', payload: index })
							}
							onAddField={handleAddField}
							onRemoveField={(index) =>
								dispatch({ type: 'REMOVE_FIELD', payload: index })
							}
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
				<div className="w-80 border-l bg-muted/30 overflow-y-auto p-4">
					{selectedField ? (
						<FieldConfigPanel
							field={selectedField}
							onUpdate={(updates) =>
								dispatch({
									type: 'UPDATE_FIELD',
									payload: {
										index: state.selectedFieldIndex!,
										updates,
									},
								})
							}
							onDelete={() =>
								dispatch({
									type: 'REMOVE_FIELD',
									payload: state.selectedFieldIndex!,
								})
							}
							onOpenTableSettings={() =>
								dispatch({ type: 'SELECT_FIELD', payload: null })
							}
						/>
					) : (
						<TableSettingsPanel
							tableName={state.tableName}
							description={state.description}
							icon={state.icon}
							autonameMethod={state.autonameMethod}
							titleField={state.titleField}
							fields={state.fields}
							isEdit={isEdit}
							onTableNameChange={(v) =>
								dispatch({ type: 'SET_TABLE_NAME', payload: v })
							}
							onDescriptionChange={(v) =>
								dispatch({ type: 'SET_DESCRIPTION', payload: v })
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
					)}
				</div>
			</div>

			{/* Bottom action bar */}
			<div className="border-t px-6 py-3 flex items-center justify-between bg-background">
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
					{isEdit ? 'Save Changes' : 'Create Table'}
				</Button>
			</div>
		</div>
	);
}
