import type { ReactNode } from 'react';
import { Field as UiField, type FieldProps } from '@/components/ui/field';

/** How a section reads and reveals errors; owned by the wizard. */
export interface FieldApi {
  /** Message to show for a field path, or undefined when nothing should show yet. */
  error: (path: string) => string | undefined;
  touch: (path: string) => void;
}

/**
 * The wizard Field is the shared ui/field primitive (label slot, reserved
 * note row, aria wiring). The wizard always passes an explicit `id`, a
 * `label` and renders its own control with that id, and always reserves the
 * note line so errors never shift the layout.
 */
export function Field(props: FieldProps) {
  return <UiField reserveNote {...props} />;
}

export function StepLayout({ children, aside }: { children: ReactNode; aside: ReactNode }) {
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
      <div className="min-w-0 space-y-6">{children}</div>
      <aside aria-label="Preview" className="min-w-0 space-y-4 lg:sticky lg:top-4 lg:self-start">
        {aside}
      </aside>
    </div>
  );
}

export function Section({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return (
    <section className="space-y-3 rounded-md border border-line bg-panel p-4">
      <div>
        <h3 className="text-sm font-semibold text-ink">{title}</h3>
        {description && <p className="text-xs text-steel">{description}</p>}
      </div>
      {children}
    </section>
  );
}
