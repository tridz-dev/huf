/** The "Saved / Unsaved" status belongs to someone who can change the flow: a viewer has nothing to save, and a phone edits nothing. */
export function showSaveStatus({ hasFlow, isPhone, canManage }: { hasFlow: boolean; isPhone: boolean; canManage: boolean }): boolean {
  return hasFlow && !isPhone && canManage;
}
