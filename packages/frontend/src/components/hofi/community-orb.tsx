"use client";

// Static particle positions to prevent hydration mismatches
import { cn } from "@/lib/utils";

interface CommunityOrbProps {
  health: number; // 0-100
  className?: string;
}

export function CommunityOrb({ health, className }: CommunityOrbProps) {
  // Determine orb state based on health
  const getOrbState = () => {
    if (health >= 80) return "thriving";
    if (health >= 60) return "healthy";
    if (health >= 40) return "growing";
    return "nurturing";
  };

  const orbState = getOrbState();

  return (
    <div className={cn("relative flex items-center justify-center", className)}>
      {/* Outer glow rings */}
      <div className="absolute h-64 w-64 animate-pulse rounded-full bg-hofi-orb-glow/20 blur-3xl" />
      <div
        className="absolute h-48 w-48 rounded-full bg-hofi-orb-glow/30 blur-2xl"
        style={{ animation: "pulse 3s ease-in-out infinite" }}
      />

      {/* Main orb */}
      <div className="relative flex h-40 w-40 items-center justify-center rounded-full bg-gradient-to-br from-hofi-orb/80 to-hofi-nature/90 shadow-2xl">
        {/* Inner glow */}
        <div className="absolute inset-2 rounded-full bg-gradient-to-tr from-transparent via-background/10 to-background/30" />

        {/* Health indicator ring */}
        <svg className="absolute h-44 w-44" viewBox="0 0 100 100">
          <circle
            cx="50"
            cy="50"
            r="46"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            className="text-border/30"
          />
          <circle
            cx="50"
            cy="50"
            r="46"
            fill="none"
            stroke="currentColor"
            strokeWidth="3"
            strokeLinecap="round"
            strokeDasharray={`${health * 2.89} 289`}
            transform="rotate(-90 50 50)"
            className="text-primary-foreground/80 transition-all duration-1000"
          />
        </svg>

        {/* Center content */}
        <div className="relative z-10 flex flex-col items-center text-primary-foreground">
          <span className="text-4xl font-light">{health}</span>
          <span className="text-xs uppercase tracking-widest opacity-80">
            {orbState}
          </span>
        </div>
      </div>

      {/* Floating particles - static positions for consistent hydration */}
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute h-1.5 w-1.5 rounded-full bg-hofi-orb/60 left-[35%] top-[42%] animate-[orb-float_3s_ease-in-out_infinite]" />
        <div className="absolute h-1.5 w-1.5 rounded-full bg-hofi-orb/60 left-[58%] top-[38%] animate-[orb-float_3.5s_ease-in-out_infinite_0.3s]" />
        <div className="absolute h-1.5 w-1.5 rounded-full bg-hofi-orb/60 left-[45%] top-[55%] animate-[orb-float_4s_ease-in-out_infinite_0.6s]" />
        <div className="absolute h-1.5 w-1.5 rounded-full bg-hofi-orb/60 left-[62%] top-[48%] animate-[orb-float_4.5s_ease-in-out_infinite_0.9s]" />
        <div className="absolute h-1.5 w-1.5 rounded-full bg-hofi-orb/60 left-[40%] top-[35%] animate-[orb-float_5s_ease-in-out_infinite_1.2s]" />
        <div className="absolute h-1.5 w-1.5 rounded-full bg-hofi-orb/60 left-[52%] top-[60%] animate-[orb-float_5.5s_ease-in-out_infinite_1.5s]" />
      </div>
    </div>
  );
}
