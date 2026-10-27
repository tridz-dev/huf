/** Props every labelled control needs to point at its note and flag an error. */
export const controlA11y = (id: string, error?: string) => ({
  id,
  'aria-describedby': `${id}-note`,
  'aria-invalid': error ? true : undefined,
});
