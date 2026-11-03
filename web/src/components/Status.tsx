export function ErrorMessage({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <p className="error" role="alert">
      {error}
    </p>
  );
}

export function Loading({ label }: { label: string }) {
  return (
    <p className="muted" role="status">
      {label}
    </p>
  );
}
