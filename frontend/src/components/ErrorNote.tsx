export function ErrorNote({ error }: { error: Error | null | undefined }) {
  if (!error) return null;
  return (
    <p role="alert" className="rounded-xl bg-danger-light px-4 py-2.5 text-sm text-danger">
      {error.message}
    </p>
  );
}
