import type { ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-primary text-white hover:bg-primary-dark disabled:bg-primary/50",
  secondary: "bg-surface text-ink hover:bg-primary-light disabled:text-ink-muted",
  ghost: "text-ink-muted hover:bg-surface hover:text-ink",
  danger: "bg-danger text-white hover:bg-danger/90 disabled:bg-danger/50",
};

export function Button({
  variant = "primary",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-medium",
        "transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
        "disabled:cursor-not-allowed",
        VARIANTS[variant],
        className,
      )}
      {...props}
    />
  );
}
