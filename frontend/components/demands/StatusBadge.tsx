"use client";

import { Badge } from "@/components/ui/badge";
import {
  DEMAND_STATUS_BADGE,
  DEMAND_STATUS_LABELS,
  type DemandStatus,
} from "@/lib/types";

export function StatusBadge({ status }: { status: DemandStatus }) {
  return (
    <Badge variant={DEMAND_STATUS_BADGE[status]}>
      {DEMAND_STATUS_LABELS[status]}
    </Badge>
  );
}
