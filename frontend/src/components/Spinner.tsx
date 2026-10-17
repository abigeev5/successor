import { LoaderCircle } from "lucide-react";

export function FullPageSpinner() {
  return (
    <div className="flex h-full items-center justify-center text-ink-muted" role="status">
      <LoaderCircle className="size-6 animate-spin" aria-hidden />
      <span className="sr-only">Загрузка…</span>
    </div>
  );
}
