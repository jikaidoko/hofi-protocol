"use client";

import { useState } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  TrendingUp,
  Users,
  Eye,
  Shield,
  User,
  Leaf,
  UtensilsCrossed,
  BookOpen,
  Heart,
  Hammer,
  HandHeart,
  PawPrint,
  Mountain,
  Package,
} from "lucide-react";
import type { ActivityItem, SocialYieldMetric, UserRole, CareCategory } from "@/lib/mock-data";
import { ACTIVITY_CATEGORIES } from "@/lib/mock-data";
import { cn } from "@/lib/utils";

interface HolonViewProps {
  activities: ActivityItem[];
  socialYield: SocialYieldMetric[];
  userRole: UserRole;
}

const categoryIcons: Record<CareCategory, React.ComponentType<{ className?: string }>> = {
  gardening: Leaf,
  cooking: UtensilsCrossed,
  teaching: BookOpen,
  healing: Heart,
  building: Hammer,
  caring: HandHeart,
  animals: PawPrint,
  land: Mountain,
  resources: Package,
};

// Helper to get approximate time for member view
function getApproximateTime(timestamp: string): string {
  if (timestamp.includes("min")) return "just now";
  if (timestamp.includes("1 hour")) return "this morning";
  if (timestamp.includes("2 hour")) return "this morning";
  if (timestamp.includes("3 hour")) return "earlier today";
  if (timestamp.includes("4 hour")) return "earlier today";
  if (timestamp.includes("5 hour")) return "earlier today";
  return "today";
}

// Helper to get vague amount range for member view
function getAmountRange(amount: number): string {
  if (amount < 30) return "20-40 HOCA";
  if (amount < 50) return "40-60 HOCA";
  if (amount < 70) return "60-80 HOCA";
  return "80-100 HOCA";
}

export function HolonView({ activities, socialYield, userRole }: HolonViewProps) {
  const [selectedActivity, setSelectedActivity] = useState<ActivityItem | null>(null);
  const [hoveredCategory, setHoveredCategory] = useState<CareCategory | null>(null);

  // Group activities by category for bubble display
  const groupedActivities = activities.reduce((acc, activity) => {
    if (!acc[activity.category]) {
      acc[activity.category] = [];
    }
    acc[activity.category].push(activity);
    return acc;
  }, {} as Record<CareCategory, ActivityItem[]>);

  const handleBubbleClick = (activity: ActivityItem) => {
    if (userRole === "guest") return; // Guests cannot open detail sheet
    setSelectedActivity(activity);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="text-center">
        <h2 className="text-2xl font-light tracking-tight">The Holon</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Care Economy & Governance
        </p>
      </div>

      {/* Current Access Level */}
      <Card className="p-4 border-border/30 bg-card/50 backdrop-blur-sm">
        <div className="flex items-center gap-3">
          {userRole === "guest" && (
            <>
              <div className="h-10 w-10 rounded-full bg-muted flex items-center justify-center">
                <Eye className="h-5 w-5 text-muted-foreground" />
              </div>
              <div>
                <p className="text-sm font-medium">Guest View</p>
                <p className="text-xs text-muted-foreground">
                  See care activity patterns, no individual data
                </p>
              </div>
            </>
          )}
          {userRole === "member" && (
            <>
              <div className="h-10 w-10 rounded-full bg-primary/20 flex items-center justify-center">
                <User className="h-5 w-5 text-primary" />
              </div>
              <div>
                <p className="text-sm font-medium">Member View</p>
                <p className="text-xs text-muted-foreground">
                  See approximate times and amount ranges
                </p>
              </div>
            </>
          )}
          {userRole === "guardian" && (
            <>
              <div className="h-10 w-10 rounded-full bg-accent/20 flex items-center justify-center">
                <Shield className="h-5 w-5 text-accent" />
              </div>
              <div>
                <p className="text-sm font-medium">Guardian View</p>
                <p className="text-xs text-muted-foreground">
                  Full transparency: names, amounts, descriptions
                </p>
              </div>
            </>
          )}
        </div>
      </Card>

      {/* Social Yield Metrics */}
      <div className="grid grid-cols-2 gap-3">
        {socialYield.map((metric) => (
          <Card
            key={metric.label}
            className="p-4 border-border/30 bg-card/50 backdrop-blur-sm"
          >
            <p className="text-xs text-muted-foreground uppercase tracking-wide">
              {metric.label}
            </p>
            <div className="flex items-baseline gap-1 mt-1">
              <span className="text-2xl font-light">{metric.value}</span>
              <span className="text-xs text-muted-foreground">{metric.unit}</span>
            </div>
            <div className="flex items-center gap-1 mt-2">
              <TrendingUp className="h-3 w-3 text-primary" />
              <span className="text-xs text-primary">+{metric.change}%</span>
            </div>
          </Card>
        ))}
      </div>

      {/* Care Bubbles by Category */}
      <div className="space-y-3">
        <div className="flex items-center justify-between px-1">
          <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wide">
            Today&apos;s Care Activity
          </h3>
          <div className="flex items-center gap-1.5">
            <Users className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="text-xs text-muted-foreground">
              {activities.length} acts
            </span>
          </div>
        </div>

        {/* Category hover tooltip */}
        {hoveredCategory && userRole === "guest" && (
          <div className="text-center">
            <Badge variant="secondary" className="text-xs">
              {ACTIVITY_CATEGORIES[hoveredCategory].label}
            </Badge>
          </div>
        )}

        <Card className="p-6 border-border/30 bg-card/50 backdrop-blur-sm">
          <div className="flex flex-wrap gap-3 justify-center">
            {Object.entries(groupedActivities).map(([category, categoryActivities]) => {
              const CategoryIcon = categoryIcons[category as CareCategory];
              const categoryData = ACTIVITY_CATEGORIES[category as CareCategory];

              return categoryActivities.map((activity) => (
                <button
                  key={activity.id}
                  onClick={() => handleBubbleClick(activity)}
                  onMouseEnter={() => setHoveredCategory(category as CareCategory)}
                  onMouseLeave={() => setHoveredCategory(null)}
                  className={cn(
                    "relative h-12 w-12 rounded-full flex items-center justify-center transition-all duration-300",
                    categoryData.bgColor,
                    userRole !== "guest" && "hover:scale-110 cursor-pointer",
                    userRole === "guest" && "cursor-default"
                  )}
                >
                  <CategoryIcon className="h-5 w-5 text-white" />
                  {/* Pulse animation for recent activities */}
                  {activity.timestamp.includes("min") && (
                    <span className="absolute inset-0 rounded-full animate-ping opacity-20 bg-white" />
                  )}
                </button>
              ));
            })}
          </div>

          {/* Legend */}
          <div className="mt-6 pt-4 border-t border-border/30">
            <div className="flex flex-wrap gap-2 justify-center">
              {Object.entries(ACTIVITY_CATEGORIES).map(([key, { label, bgColor }]) => {
                const hasActivities = groupedActivities[key as CareCategory]?.length > 0;
                if (!hasActivities) return null;
                return (
                  <div key={key} className="flex items-center gap-1.5">
                    <div className={cn("h-2 w-2 rounded-full", bgColor)} />
                    <span className="text-[10px] text-muted-foreground">{label}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </Card>
      </div>

      {/* Activity Detail Sheet - Only for members and guardians */}
      <Sheet open={!!selectedActivity} onOpenChange={() => setSelectedActivity(null)}>
        <SheetContent side="bottom" className="rounded-t-3xl">
          <SheetHeader>
            <SheetTitle className="text-left">Care Activity Detail</SheetTitle>
            <SheetDescription className="sr-only">
              View details about this care activity based on your access level
            </SheetDescription>
          </SheetHeader>

          {selectedActivity && (
            <div className="mt-4 space-y-4">
              {/* Category Badge */}
              <div className="flex items-center gap-2">
                {(() => {
                  const CategoryIcon = categoryIcons[selectedActivity.category];
                  const categoryData = ACTIVITY_CATEGORIES[selectedActivity.category];
                  return (
                    <>
                      <div className={cn("h-10 w-10 rounded-full flex items-center justify-center", categoryData.bgColor)}>
                        <CategoryIcon className="h-5 w-5 text-white" />
                      </div>
                      <div>
                        <p className="font-medium">{categoryData.label}</p>
                        <p className="text-xs text-muted-foreground">Care Category</p>
                      </div>
                    </>
                  );
                })()}
              </div>

              {/* Member View: Approximate data */}
              {userRole === "member" && (
                <div className="space-y-3 p-4 rounded-xl bg-muted/30">
                  <div className="flex justify-between">
                    <span className="text-sm text-muted-foreground">When</span>
                    <span className="text-sm font-medium">
                      {getApproximateTime(selectedActivity.timestamp)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-muted-foreground">Value Range</span>
                    <span className="text-sm font-medium">
                      {getAmountRange(selectedActivity.amount)}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground italic pt-2 border-t border-border/30">
                    Member names are protected by holon privacy settings
                  </p>
                </div>
              )}

              {/* Guardian View: Full detail */}
              {userRole === "guardian" && (
                <div className="space-y-3 p-4 rounded-xl bg-muted/30">
                  <div className="flex justify-between">
                    <span className="text-sm text-muted-foreground">Member</span>
                    <span className="text-sm font-medium">{selectedActivity.memberName}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-muted-foreground">Exact Time</span>
                    <span className="text-sm font-medium">
                      {new Date(selectedActivity.exactTime).toLocaleTimeString("en-US", {
                        hour: "numeric",
                        minute: "2-digit",
                        hour12: true,
                      })}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-muted-foreground">HOCA Earned</span>
                    <span className="text-sm font-medium text-primary">
                      {selectedActivity.amount} HOCA
                    </span>
                  </div>
                  <div className="pt-2 border-t border-border/30">
                    <span className="text-sm text-muted-foreground">Description</span>
                    <p className="text-sm mt-1">{selectedActivity.description}</p>
                  </div>
                </div>
              )}
            </div>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
