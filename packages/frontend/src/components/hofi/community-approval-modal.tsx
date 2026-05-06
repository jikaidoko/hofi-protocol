"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Card } from "@/components/ui/card";
import {
  CheckCircle2,
  Clock,
  Users,
  Leaf,
  Heart,
  UtensilsCrossed,
  BookOpen,
  Hammer,
  HandHeart,
  PawPrint,
  Mountain,
  Package,
  Sparkles,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ─── Types ──────────────────────────────────────────────────────────────────

export interface PendingTask {
  id: string;
  description: string;
  memberName: string;
  memberAvatar: string;
  category: string;
  duration: number;
  tenzoConfidence: number;
  tenzoReasoning: string;
  suggestedReward: number;
  submittedAt: string;
  approvalsRequired: number;
  approvals: { memberName: string; memberAvatar: string; approvedAt: string }[];
  myVote: "approved" | "none";
}

export interface HolonApprovalRules {
  holonName: string;
  requiredApprovals: number;
  totalMembers: number;
  spirit: string;
}

interface CommunityApprovalModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  pendingTasks: PendingTask[];
  holonRules: HolonApprovalRules;
  currentUserName: string;
  currentUserAvatar: string;
  onApprove: (taskId: string) => void;
  onActivateReward: (taskId: string) => void;
}

// ─── Category icons ─────────────────────────────────────────────────────────

const categoryIcons: Record<string, LucideIcon> = {
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

// ─── Component ──────────────────────────────────────────────────────────────

export function CommunityApprovalModal({
  open,
  onOpenChange,
  pendingTasks,
  holonRules,
  currentUserName,
  currentUserAvatar,
  onApprove,
  onActivateReward,
}: CommunityApprovalModalProps) {
  const [expandedTask, setExpandedTask] = useState<string | null>(null);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[85vh] overflow-hidden bg-card border-border/50 flex flex-col">
        <DialogHeader className="flex-shrink-0">
          <DialogTitle className="text-xl font-light flex items-center gap-2">
            <Users className="h-5 w-5 text-primary" />
            Community Approval
          </DialogTitle>
          <DialogDescription className="text-muted-foreground">
            {holonRules.spirit}
          </DialogDescription>
        </DialogHeader>

        {/* Rules reminder */}
        <div className="flex-shrink-0 flex items-center gap-3 px-3 py-2.5 rounded-xl bg-primary/5 border border-primary/15">
          <ShieldCheck className="h-4 w-4 text-primary flex-shrink-0" />
          <p className="text-xs text-muted-foreground leading-relaxed">
            <span className="font-medium text-foreground">{holonRules.holonName}</span>
            {" "}requires{" "}
            <span className="font-semibold text-primary">{holonRules.requiredApprovals}</span>
            {" "}of{" "}
            <span className="font-medium">{holonRules.totalMembers}</span>
            {" "}members to approve before activating a reward.
            Each voice matters equally.
          </p>
        </div>

        {/* Task list */}
        <div className="flex-1 overflow-y-auto space-y-3 pr-1 -mr-1">
          {pendingTasks.length === 0 ? (
            <div className="flex flex-col items-center py-12 text-center">
              <Sparkles className="h-10 w-10 text-muted-foreground/30 mb-3" />
              <p className="text-sm text-muted-foreground">
                No pending tasks to review
              </p>
              <p className="text-xs text-muted-foreground/60 mt-1">
                When a member submits care work for community evaluation, it will appear here.
              </p>
            </div>
          ) : (
            pendingTasks.map((task) => (
              <TaskCard
                key={task.id}
                task={task}
                holonRules={holonRules}
                expanded={expandedTask === task.id}
                onToggleExpand={() =>
                  setExpandedTask(expandedTask === task.id ? null : task.id)
                }
                onApprove={() => onApprove(task.id)}
                onActivateReward={() => onActivateReward(task.id)}
              />
            ))
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ─── Task Card ──────────────────────────────────────────────────────────────

function TaskCard({
  task,
  holonRules,
  expanded,
  onToggleExpand,
  onApprove,
  onActivateReward,
}: {
  task: PendingTask;
  holonRules: HolonApprovalRules;
  expanded: boolean;
  onToggleExpand: () => void;
  onApprove: () => void;
  onActivateReward: () => void;
}) {
  const CategoryIcon = categoryIcons[task.category] || HandHeart;
  const approvalCount = task.approvals.length;
  const majorityReached = approvalCount >= holonRules.requiredApprovals;
  const alreadyApproved = task.myVote === "approved";
  const approvalProgress = Math.min(
    (approvalCount / holonRules.requiredApprovals) * 100,
    100
  );

  return (
    <Card
      className={cn(
        "p-4 border-border/30 transition-all",
        expanded ? "bg-card" : "bg-card/50 hover:bg-card/80"
      )}
    >
      {/* Header row — always visible */}
      <button
        onClick={onToggleExpand}
        className="w-full text-left"
      >
        <div className="flex items-start gap-3">
          {/* Member avatar */}
          <Avatar className="h-10 w-10 flex-shrink-0">
            <AvatarFallback className="text-sm bg-accent/10 text-accent">
              {task.memberAvatar}
            </AvatarFallback>
          </Avatar>

          <div className="flex-1 min-w-0">
            {/* Name + category */}
            <div className="flex items-center gap-2">
              <span className="font-medium text-sm">{task.memberName}</span>
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                <CategoryIcon className="h-3 w-3" />
                <span className="capitalize">{task.category}</span>
              </div>
            </div>

            {/* Description (truncated when collapsed) */}
            <p
              className={cn(
                "text-sm text-muted-foreground mt-1",
                !expanded && "line-clamp-1"
              )}
            >
              {task.description}
            </p>

            {/* Quick stats row */}
            <div className="flex items-center gap-3 mt-2">
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                <Clock className="h-3 w-3" />
                <span>{task.duration}h</span>
              </div>
              <div className="flex items-center gap-1 text-xs text-primary">
                <Leaf className="h-3 w-3" />
                <span>{task.suggestedReward} HOCA</span>
              </div>
              <div className="flex items-center gap-1 text-xs">
                <Users className="h-3 w-3 text-muted-foreground" />
                <span
                  className={cn(
                    "font-medium",
                    majorityReached
                      ? "text-primary"
                      : "text-muted-foreground"
                  )}
                >
                  {approvalCount}/{holonRules.requiredApprovals}
                </span>
              </div>
            </div>
          </div>
        </div>
      </button>

      {/* Expanded details */}
      {expanded && (
        <div className="mt-4 space-y-3 border-t border-border/30 pt-4">
          {/* Tenzo reasoning */}
          <div className="flex gap-2.5 p-3 rounded-lg bg-muted/30">
            <div className="flex-shrink-0 h-6 w-6 rounded-full bg-primary/15 flex items-center justify-center mt-0.5">
              <Sparkles className="h-3 w-3 text-primary" />
            </div>
            <div className="flex-1">
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium mb-1">
                Tenzo Assessment
              </p>
              <p className="text-sm text-foreground/80 leading-relaxed">
                {task.tenzoReasoning}
              </p>
              <div className="flex items-center gap-3 mt-2 text-xs text-muted-foreground">
                <span>
                  Confidence:{" "}
                  <span className="font-medium text-foreground">
                    {Math.round(task.tenzoConfidence * 100)}%
                  </span>
                </span>
                <span>
                  Suggested:{" "}
                  <span className="font-medium text-primary">
                    {task.suggestedReward} HOCA
                  </span>
                </span>
              </div>
            </div>
          </div>

          {/* Approval progress bar */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">Approval progress</span>
              <span
                className={cn(
                  "font-medium",
                  majorityReached ? "text-primary" : "text-muted-foreground"
                )}
              >
                {approvalCount} of {holonRules.requiredApprovals} needed
              </span>
            </div>
            <div className="h-2 rounded-full bg-muted/50 overflow-hidden">
              <div
                className={cn(
                  "h-full rounded-full transition-all duration-500",
                  majorityReached
                    ? "bg-primary"
                    : "bg-primary/40"
                )}
                style={{ width: `${approvalProgress}%` }}
              />
            </div>

            {/* Who already approved */}
            {task.approvals.length > 0 && (
              <div className="flex items-center gap-1.5 mt-1">
                <span className="text-[10px] text-muted-foreground">Approved by:</span>
                <div className="flex -space-x-1.5">
                  {task.approvals.map((a, i) => (
                    <Avatar key={i} className="h-5 w-5 border-2 border-card">
                      <AvatarFallback className="text-[8px] bg-primary/10 text-primary">
                        {a.memberAvatar}
                      </AvatarFallback>
                    </Avatar>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Action buttons */}
          <div className="flex gap-2 pt-1">
            <Button
              onClick={(e) => {
                e.stopPropagation();
                onApprove();
              }}
              disabled={alreadyApproved}
              variant={alreadyApproved ? "outline" : "default"}
              className={cn(
                "flex-1 h-10 rounded-xl transition-all",
                alreadyApproved
                  ? "border-primary/30 text-primary bg-primary/5 cursor-default"
                  : "bg-primary hover:bg-primary/90 text-primary-foreground"
              )}
            >
              <CheckCircle2
                className={cn(
                  "h-4 w-4 mr-2",
                  alreadyApproved && "text-primary"
                )}
              />
              {alreadyApproved ? "Approved" : "Approve"}
            </Button>

            <Button
              onClick={(e) => {
                e.stopPropagation();
                onActivateReward();
              }}
              disabled={!majorityReached}
              variant="outline"
              className={cn(
                "flex-1 h-10 rounded-xl transition-all",
                majorityReached
                  ? "border-primary/50 text-primary hover:bg-primary/10"
                  : "border-border/30 text-muted-foreground/40 cursor-not-allowed"
              )}
            >
              <Leaf className="h-4 w-4 mr-2" />
              Activate Reward
            </Button>
          </div>

          {/* Time since submitted */}
          <p className="text-[10px] text-muted-foreground/60 text-center">
            Submitted {task.submittedAt}
          </p>
        </div>
      )}
    </Card>
  );
}
