import type { DataTableFieldDef, DataTableSchema } from '@/types/dataTable.types';
import { isExistingField, type OriginalFields } from './fieldRules';

export interface BuilderState {
	tableName: string;
	description: string;
	tableGroup: string;
	icon: string;
	autonameMethod: string;
	titleField: string;
	fields: DataTableFieldDef[];
	selectedFieldIndex: number | null;
	isDirty: boolean;
	registryName: string;
	/** Fields as loaded (edit mode): their fieldname is locked and deleting them loses data. */
	originalFields: OriginalFields;
}

export type BuilderAction =
	| { type: 'SET_TABLE_NAME'; payload: string }
	| { type: 'SET_DESCRIPTION'; payload: string }
	| { type: 'SET_TABLE_GROUP'; payload: string }
	| { type: 'SET_ICON'; payload: string }
	| { type: 'SET_AUTONAME_METHOD'; payload: string }
	| { type: 'SET_TITLE_FIELD'; payload: string }
	| { type: 'ADD_FIELD'; payload: DataTableFieldDef }
	| { type: 'UPDATE_FIELD'; payload: { index: number; updates: Partial<DataTableFieldDef> } }
	| { type: 'REMOVE_FIELD'; payload: number }
	| { type: 'REORDER_FIELDS'; payload: { from: number; to: number } }
	| { type: 'SELECT_FIELD'; payload: number | null }
	| { type: 'LOAD_SCHEMA'; payload: DataTableSchema }
	| { type: 'MARK_CLEAN' };

export const initialBuilderState: BuilderState = {
	tableName: '',
	description: '',
	tableGroup: '',
	icon: '',
	autonameMethod: 'Autoincrement',
	titleField: '',
	fields: [],
	selectedFieldIndex: null,
	isDirty: false,
	registryName: '',
	originalFields: {},
};

export function builderReducer(state: BuilderState, action: BuilderAction): BuilderState {
	switch (action.type) {
		case 'SET_TABLE_NAME':
			return { ...state, tableName: action.payload, isDirty: true };
		case 'SET_DESCRIPTION':
			return { ...state, description: action.payload, isDirty: true };
		case 'SET_TABLE_GROUP':
			return { ...state, tableGroup: action.payload, isDirty: true };
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
			const { index } = action.payload;
			const current = state.fields[index];
			if (!current) return state;
			const updates = { ...action.payload.updates };
			// DATA-LOSS GUARD: the fieldname of a loaded field is its column name.
			if (isExistingField(current, state.originalFields)) delete updates.fieldname;
			const newFields = [...state.fields];
			newFields[index] = { ...current, ...updates };
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
			return { ...state, fields: newFields, selectedFieldIndex: newSelected, isDirty: true };
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
				tableGroup: action.payload.table_group || '',
				icon: action.payload.icon || '',
				autonameMethod: action.payload.autoname_method || 'Autoincrement',
				titleField: action.payload.title_field_name || '',
				fields: action.payload.fields,
				registryName: action.payload.name,
				originalFields: Object.fromEntries(action.payload.fields.map((f) => [f.fieldname, f.fieldtype])),
				selectedFieldIndex: null,
				isDirty: false,
			};
		case 'MARK_CLEAN':
			return { ...state, isDirty: false };
		default:
			return state;
	}
}
