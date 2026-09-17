import type { ReactNode } from 'react';

// A persistent label for a settings input -- a placeholder disappears once a
// field has a value. Uses the host's shared `field-labeled` styles.
export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="field-labeled">
      <span className="field-labeled-label">{label}</span>
      {children}
    </label>
  );
}
