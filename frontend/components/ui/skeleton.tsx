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
      className={cn("rounded-md bg-muted mn-shimmer", className)}
      {...props}
    />
  );
}

export { Skeleton };
