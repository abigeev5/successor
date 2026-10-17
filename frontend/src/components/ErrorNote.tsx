export function ErrorNote({ error }: { error: Error | null | undefined }) {
  if (!error) return null;
  return (
    <p role="alert" className="rounded-md bg-danger-light px-3 py-2 text-sm text-danger">
      {error.message}
    </p>
  );
}
