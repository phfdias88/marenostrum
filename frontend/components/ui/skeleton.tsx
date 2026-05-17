import { cn } from "@/lib/utils";

/**
 * Placeholder animado (shadcn padrao). Usado em loaders.
 */
function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("animate-pulse rounded-md bg-muted", className)}
      {...props}
    />
  );
}

export { Skeleton };
