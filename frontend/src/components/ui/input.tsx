import type { InputHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

export type FieldOptions = { fit?: boolean; compact?: boolean; withIcon?: boolean };

export function fieldClass({ fit = false, compact = false, withIcon = false }: FieldOptions = {}) {
  return cn(
    "rounded-xl border border-line bg-white text-ink transition-colors placeholder:text-ink-soft",
    "focus:border-primary focus:outline-none focus:ring-4 focus:ring-primary-light/70",
    fit ? "w-auto" : "w-full",
    compact
      ? "px-2 py-1 text-xs"
      : withIcon
        ? "py-2.5 pr-3.5 pl-9 text-sm"
        : "px-3.5 py-2.5 text-sm",
  );
}

export function Input({
  fit,
  compact,
  withIcon,
  className,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & FieldOptions) {
  return <input className={cn(fieldClass({ fit, compact, withIcon }), className)} {...props} />;
}

export function Label({ htmlFor, children }: { htmlFor: string; children: React.ReactNode }) {
  return (
    <label htmlFor={htmlFor} className="mb-1.5 block text-xs font-medium text-ink-muted">
      {children}
    </label>
  );
}
