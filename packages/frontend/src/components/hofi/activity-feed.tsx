"use client";

import { useState, useMemo } from "react";
import { Card } from "@/components/ui/card";
import {
  Leaf,
  UtensilsCrossed,
  BookOpen,
  Heart,
  Hammer,
  HandHeart,
  PawPrint,
  Mountain,
  Package,
  X,
  TrendingUp,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { ActivityItem, CareCategory } from "@/lib/mock-data";
import { ACTIVITY_CATEGORIES } from "@/lib/mock-data";

const categoryIcons: Record<CareCategory, typeof Leaf> = {
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

interface ActivityFeedProps {
  activities: ActivityItem[];
  isMember: boolean;
}

interface GroupedActivity {
  category: CareCategory;
  count: number;
  totalAmount: number;
  items: ActivityItem[];
}

export function ActivityFeed({ activities, isMember }: ActivityFeedProps) {
  const [selectedGroup, setSelectedGroup] = useState<GroupedActivity | null>(null);

  // Group activities by category
  const groupedActivities = useMemo(() => {
    const groups: Record<string, GroupedActivity> = {};
    
    activities.forEach((activity) => {
      if (!groups[activity.category]) {
        groups[activity.category] = {
          category: activity.category,
          count: 0,
          totalAmount: 0,
          items: [],
        };
      }
      groups[activity.category].count += 1;
      groups[activity.category].totalAmount += activity.amount;
      groups[activity.category].items.push(activity);
    });

    return Object.values(groups).sort((a, b) => b.count - a.count);
  }, [activities]);

  // Aggregate stats for non-members
  const aggregateStats = useMemo(() => {
    const totalActs = activities.length;
    const totalHoca = activities.reduce((sum, a) => sum + a.amount, 0);
    const mostActive = groupedActivities[0];
    return { totalActs, totalHoca, mostActive };
  }, [activities, groupedActivities]);

  const handleBubbleClick = (group: GroupedActivity) => {
    if (isMember) {
      setSelectedGroup(group);
    }
  };

  // Non-member view: only aggregate stats
  if (!isMember) {
    return (
      <div className="space-y-4">
        <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wide px-1">
          Community Activity
        </h3>
        <Card className="p-5 border-border/30 bg-card/50 backdrop-blur-sm">
          <div className="grid grid-cols-3 gap-4 text-center">
            <div>
              <p className="text-2xl font-light">{aggregateStats.totalActs}</p>
              <p className="text-xs text-muted-foreground">Care acts today</p>
            </div>
            <div>
              <p className="text-2xl font-light">{aggregateStats.totalHoca}</p>
              <p className="text-xs text-muted-foreground">HOCA distributed</p>
            </div>
            <div className="flex flex-col items-center">
              {aggregateStats.mostActive && (
                <>
                  <div
                    className={cn(
                      "h-8 w-8 rounded-full flex items-center justify-center mb-1",
                      ACTIVITY_CATEGORIES[aggregateStats.mostActive.category].bgColor
                    )}
                  >
                    {(() => {
                      const Icon = categoryIcons[aggregateStats.mostActive.category];
                      return <Icon className="h-4 w-4 text-white" />;
                    })()}
                  </div>
                  <p className="text-xs text-muted-foreground">Most active</p>
                </>
              )}
            </div>
          </div>
        </Card>
        <p className="text-xs text-center text-muted-foreground/60 px-4">
          Join the holon to see detailed activity
        </p>
      </div>
    );
  }

  // Member view: anonymous bubbles grouped by category
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between px-1">
        <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wide">
          Value Minted
        </h3>
        <div className="flex items-center gap-1 text-xs text-primary">
          <TrendingUp className="h-3 w-3" />
          <span>{aggregateStats.totalHoca} HOCA today</span>
        </div>
      </div>

      {/* Bubble Grid */}
      <div className="flex flex-wrap gap-3 justify-center py-2">
        {groupedActivities.map((group) => {
          const Icon = categoryIcons[group.category];
          const categoryInfo = ACTIVITY_CATEGORIES[group.category];
          // Scale bubble size based on count (min 40px, max 72px)
          const size = Math.min(72, Math.max(40, 32 + group.count * 12));

          return (
            <button
              key={group.category}
              onClick={() => handleBubbleClick(group)}
              className={cn(
                "rounded-full flex items-center justify-center transition-all duration-300",
                "hover:scale-110 hover:shadow-lg active:scale-95",
                "focus:outline-none focus:ring-2 focus:ring-primary/50",
                categoryInfo.bgColor
              )}
              style={{ width: size, height: size }}
              aria-label={`${group.count} ${categoryInfo.label} activities`}
            >
              <Icon className="text-white" style={{ width: size * 0.4, height: size * 0.4 }} />
            </button>
          );
        })}
      </div>

      {/* Category Legend */}
      <div className="flex flex-wrap gap-2 justify-center">
        {groupedActivities.map((group) => {
          const categoryInfo = ACTIVITY_CATEGORIES[group.category];
          return (
            <span
              key={group.category}
              className={cn(
                "text-xs px-2 py-0.5 rounded-full bg-muted/50",
                categoryInfo.color
              )}
            >
              {group.count} {categoryInfo.label}
            </span>
          );
        })}
      </div>

      {/* Slide-up Detail Panel */}
      {selectedGroup && (
        <div
          className="fixed inset-0 z-50 bg-black/20 backdrop-blur-sm"
          onClick={() => setSelectedGroup(null)}
        >
          <div
            className="absolute bottom-0 left-0 right-0 bg-card border-t border-border rounded-t-3xl p-6 animate-in slide-in-from-bottom duration-300"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <div
                  className={cn(
                    "h-10 w-10 rounded-full flex items-center justify-center",
                    ACTIVITY_CATEGORIES[selectedGroup.category].bgColor
                  )}
                >
                  {(() => {
                    const Icon = categoryIcons[selectedGroup.category];
                    return <Icon className="h-5 w-5 text-white" />;
                  })()}
                </div>
                <div>
                  <h4 className="font-medium">
                    {ACTIVITY_CATEGORIES[selectedGroup.category].label}
                  </h4>
                  <p className="text-sm text-muted-foreground">
                    {selectedGroup.count} acts | {selectedGroup.totalAmount} HOCA
                  </p>
                </div>
              </div>
              <button
                onClick={() => setSelectedGroup(null)}
                className="p-2 rounded-full hover:bg-muted transition-colors"
              >
                <X className="h-5 w-5 text-muted-foreground" />
              </button>
            </div>

            <div className="space-y-2 max-h-64 overflow-y-auto">
              {selectedGroup.items.map((item) => (
                <div
                  key={item.id}
                  className="flex items-center justify-between py-2 border-b border-border/30 last:border-0"
                >
                  <div className="flex items-center gap-3">
                    <div className="h-8 w-8 rounded-full bg-muted flex items-center justify-center text-xs font-medium">
                      {item.memberAvatar}
                    </div>
                    <div>
                      <p className="text-sm font-medium">{item.memberName}</p>
                      <p className="text-xs text-muted-foreground">{item.timestamp}</p>
                    </div>
                  </div>
                  <span className="text-sm font-medium text-primary">
                    +{item.amount} HOCA
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
