import { cn } from "@/lib/cn";

export function BrandMark({ inverted = false }: { inverted?: boolean }) {
  return (
    <span
      aria-hidden
      className={cn(
        "grid size-8 place-items-center rounded-[10px] text-[15px] font-bold shadow-sm",
        inverted ? "bg-white text-primary" : "bg-sky-deep text-white",
      )}
    >
      П
    </span>
  );
}
