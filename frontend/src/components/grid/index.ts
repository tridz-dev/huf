/**
 * Data-grid patterns (DESIGN.md §6.11): editable typed grids and the tools
 * around them. Domain-free; built only from components/ui and theme tokens.
 */
export * from './types';
export { DataGrid, GRID_ROW_H, type DataGridProps } from './DataGrid';
export { CellDisplay, CellEditor, type CellEditorProps } from './GridCell';
export { useGridNav, type CellPos, type CommitResult } from './useGridNav';
export { FilterChip, SortChip, type FilterChipProps, type SortChipProps } from './FilterChip';
export { GridToolbar, MatchCount, FieldsMenu, GridFooter, type GridToolbarProps, type FieldsMenuProps } from './GridToolbar';
export { BulkActionBar, type BulkAction, type BulkActionBarProps } from './BulkActionBar';
export { RecordDrawer, type RecordDrawerProps } from './RecordDrawer';
export { PermissionMatrix, applyGrant, type MatrixSubject, type MatrixCapability, type MatrixValue, type PermissionMatrixProps } from './PermissionMatrix';
export { ImportMapper, SKIP_COLUMN, type SourceColumn, type TargetField, type RejectedRow, type ImportMapperProps } from './ImportMapper';
export { ChangeImpactNotice, type ImpactLine, type ChangeImpactNoticeProps } from './ChangeImpactNotice';
export { ConfirmDestructive, type Dependent, type ConfirmDestructiveProps } from './ConfirmDestructive';
