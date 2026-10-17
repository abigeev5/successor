import type { InputHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "w-full rounded-md border border-black/15 bg-white px-3 py-2 text-sm text-ink",
        "placeholder:text-ink-muted/60 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary-light",
        className,
      )}
      {...props}
    />
  );
}

export function Label({ htmlFor, children }: { htmlFor: string; children: React.ReactNode }) {
  return (
    <label htmlFor={htmlFor} className="mb-1 block text-sm font-medium text-ink">
      {children}
    </label>
  );
}
