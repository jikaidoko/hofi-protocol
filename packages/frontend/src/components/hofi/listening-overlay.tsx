"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

interface ListeningOverlayProps {
  active: boolean;
  onClose: () => void;
}

export function ListeningOverlay({ active, onClose }: ListeningOverlayProps) {
  // Initialize with static values to avoid hydration mismatch
  const [bars, setBars] = useState<number[]>(Array(24).fill(0.3));
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!active || !mounted) return;

    const interval = setInterval(() => {
      setBars((prev) =>
        prev.map(() => 0.2 + Math.random() * 0.8)
      );
    }, 100);

    return () => clearInterval(interval);
  }, [active, mounted]);

  if (!active) return null;

  return (
    <div className="fixed inset-0 z-50 flex flex-col items-center justify-center">
      {/* Blurred backdrop */}
      <div className="absolute inset-0 bg-background/80 backdrop-blur-xl" />

      {/* Close button */}
      <Button
        variant="ghost"
        size="icon"
        className="absolute top-4 right-4 z-10 text-muted-foreground hover:text-foreground"
        onClick={onClose}
      >
        <X className="h-6 w-6" />
      </Button>

      {/* Content */}
      <div className="relative z-10 flex flex-col items-center gap-8 px-6 text-center">
        {/* Pulsing orb */}
        <div className="relative">
          <div className="absolute inset-0 h-32 w-32 animate-ping rounded-full bg-primary/20" />
          <div className="absolute inset-0 h-32 w-32 animate-pulse rounded-full bg-primary/30 blur-xl" />
          <div className="relative h-32 w-32 rounded-full bg-gradient-to-br from-primary/60 to-accent/60 flex items-center justify-center">
            <div className="h-24 w-24 rounded-full bg-background/20 backdrop-blur-sm" />
          </div>
        </div>

        {/* Waveform visualization */}
        <div className="flex items-center justify-center gap-1 h-16 w-64">
          {bars.map((height, i) => (
            <div
              key={i}
              className="w-1.5 rounded-full bg-primary/70 transition-all duration-100"
              style={{
                height: `${height * 100}%`,
                opacity: 0.4 + height * 0.6,
              }}
            />
          ))}
        </div>

        {/* Status text */}
        <div className="space-y-2">
          <h2 className="text-2xl font-light text-foreground">Listening...</h2>
          <p className="text-sm text-muted-foreground max-w-xs">
            Describe your care activity. The community is witnessing your contribution.
          </p>
        </div>

        {/* Animated dots */}
        <div className="flex gap-2">
          <div className="h-2 w-2 rounded-full bg-primary animate-[listening-bounce_1.4s_ease-in-out_infinite]" />
          <div className="h-2 w-2 rounded-full bg-primary animate-[listening-bounce_1.4s_ease-in-out_infinite_0.16s]" />
          <div className="h-2 w-2 rounded-full bg-primary animate-[listening-bounce_1.4s_ease-in-out_infinite_0.32s]" />
        </div>
      </div>
    </div>
  );
}
