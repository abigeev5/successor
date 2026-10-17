import type { LucideIcon } from "lucide-react";

export function EmptyState({
  icon: Icon,
  title,
  children,
}: {
  icon: LucideIcon;
  title?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="mx-auto flex max-w-md flex-col items-center py-16 text-center">
      <div className="mb-4 rounded-full bg-primary-light p-3 text-primary">
        <Icon className="size-6" aria-hidden />
      </div>
      {title && <h2 className="mb-2 text-lg font-semibold">{title}</h2>}
      <p className="text-sm text-ink-muted">{children}</p>
    </div>
  );
}
