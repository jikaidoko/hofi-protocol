"use client";

import { cn } from "@/lib/utils";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { PersonalTransaction, CareCategory } from "@/lib/mock-data";
import { ACTIVITY_CATEGORIES } from "@/lib/mock-data";
import { 
  ArrowDownLeft, 
  ArrowUpRight, 
  Leaf, 
  Gift, 
  ShoppingBag,
  Send
} from "lucide-react";

interface PersonalActivityProps {
  transactions: PersonalTransaction[];
}

const typeConfig = {
  earned: {
    icon: Leaf,
    label: "Earned",
    color: "text-emerald-600",
    bgColor: "bg-emerald-500/10",
  },
  received: {
    icon: ArrowDownLeft,
    label: "Received",
    color: "text-primary",
    bgColor: "bg-primary/10",
  },
  spent: {
    icon: ShoppingBag,
    label: "Spent",
    color: "text-amber-600",
    bgColor: "bg-amber-500/10",
  },
  sent: {
    icon: Send,
    label: "Sent",
    color: "text-muted-foreground",
    bgColor: "bg-muted",
  },
};

export function PersonalActivity({ transactions }: PersonalActivityProps) {
  // Empty state — usuario autenticado sin actos de cuidado registrados.
  // Esto evita mostrar el MOCK_PERSONAL_TRANSACTIONS a un member nuevo,
  // que sería engañoso (transacciones que no son suyas).
  if (transactions.length === 0) {
    return (
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium text-muted-foreground">
            Recent Activity
          </h3>
        </div>
        <Card className="p-6 border-border/30 bg-card/50 text-center">
          <div className="mx-auto mb-3 h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">
            <Leaf className="h-5 w-5 text-primary" />
          </div>
          <p className="text-sm font-medium text-foreground">
            Aún no registraste actos de cuidado
          </p>
          <p className="text-xs text-muted-foreground mt-1.5 max-w-xs mx-auto">
            Pulsá <span className="font-medium text-foreground">Voice Register</span> o{" "}
            <span className="font-medium text-foreground">Manual Entry</span> para empezar
          </p>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-muted-foreground">
          Recent Activity
        </h3>
        <button className="text-xs text-primary hover:underline">
          View all
        </button>
      </div>

      <div className="space-y-2">
        {transactions.slice(0, 5).map((tx) => {
          const config = typeConfig[tx.type];
          const Icon = config.icon;
          const isIncoming = tx.type === "earned" || tx.type === "received";

          return (
            <Card
              key={tx.id}
              className="flex items-center gap-3 p-3 border-border/30 bg-card/50"
            >
              {/* Icon */}
              <div
                className={cn(
                  "flex h-9 w-9 items-center justify-center rounded-full",
                  config.bgColor
                )}
              >
                <Icon className={cn("h-4 w-4", config.color)} />
              </div>

              {/* Description */}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">
                  {tx.description}
                </p>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-xs text-muted-foreground">
                    {tx.timestamp}
                  </span>
                  {tx.category && (
                    <Badge
                      variant="outline"
                      className="text-[10px] px-1.5 py-0 h-4 border-border/50"
                    >
                      {ACTIVITY_CATEGORIES[tx.category].label}
                    </Badge>
                  )}
                  {tx.counterparty && (
                    <span className="text-xs text-muted-foreground">
                      {tx.type === "received" ? "from" : "to"} {tx.counterparty}
                    </span>
                  )}
                </div>
              </div>

              {/* Amount */}
              <div
                className={cn(
                  "text-sm font-semibold tabular-nums",
                  isIncoming ? "text-emerald-600" : "text-muted-foreground"
                )}
              >
                {isIncoming ? "+" : "-"}{tx.amount} HF
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
