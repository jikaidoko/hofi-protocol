"use client";

import type { ImpactCircleData, MetricScope } from "@/lib/mock-data";

interface ImpactCirclesProps {
  data: ImpactCircleData[];
  scope: MetricScope;
  compact?: boolean;
}

interface CircleConfig {
  id: string;
  fullLabel: string;
  descriptor: string;
  weekValue: number;
  allTimeValue: number;
  unit: string;
  percentChange: number;
  color: string; // hex color
}

// WCAG 4.5:1 — white text needs a dark-enough background.
// Each orb uses a dark base gradient so white achieves required contrast.
// co2 green:  #2D6B4A → #3D8A5F  (dark forest green, white contrast ~7:1)
// gnh gold:   #5C4200 → #7A5800  (dark amber, white contrast ~8:1 — fixes yellow)
// cci teal:   #1A4D6B → #235F82  (dark ocean teal, white contrast ~7:1)
const COLOR_CONFIG: Record<string, { gradientFrom: string; gradientTo: string; glowColor: string; particleColor: string }> = {
  co2: {
    gradientFrom: "#2D6B4A",
    gradientTo: "#3D8A5F",
    glowColor: "#7EC8A0",
    particleColor: "#7EC8A099",
  },
  gnh: {
    gradientFrom: "#5C4200",
    gradientTo: "#7A5800",
    glowColor: "#E8C97E",
    particleColor: "#E8C97E99",
  },
  cci: {
    gradientFrom: "#1A4D6B",
    gradientTo: "#235F82",
    glowColor: "#7AA8C8",
    particleColor: "#7AA8C899",
  },
};

// Progress ring colors — must contrast against ALL THREE dark orb backgrounds.
// Neutral gray: #D4D4D4 (light gray, ~8:1 on dark green, ~5:1 on dark amber, ~7:1 on dark teal)
// Positive:     #A8E6C3 (light sage, ~9:1 on all three dark backgrounds)
// Negative:     #F0A0A0 (light terracotta, ~6:1 on all three dark backgrounds)
const RING_NEUTRAL  = "#D4D4D4";
const RING_POSITIVE = "#A8E6C3";
const RING_NEGATIVE = "#F0A0A0";

const svgRadius = 50;
const circumference = 2 * Math.PI * svgRadius;

const formatValue = (v: number) =>
  v >= 1000
    ? `${(v / 1000).toFixed(0)}k`
    : v % 1 === 0
      ? v.toString()
      : v.toFixed(1);

const getChangeInfo = (pct: number) => {
  if (pct > 1)  return { symbol: "↑", label: `+${pct.toFixed(0)}%`, ringColor: RING_POSITIVE, labelColor: "#A8E6C3" };
  if (pct < -1) return { symbol: "↓", label: `${pct.toFixed(0)}%`,  ringColor: RING_NEGATIVE, labelColor: "#F0A0A0" };
  return             { symbol: "→", label: "—",                      ringColor: RING_NEUTRAL,  labelColor: "#D4D4D4" };
};

const getRingDash = (pct: number) => {
  const clamped = Math.max(-100, Math.min(100, pct));
  const fillRatio = (clamped + 100) / 200;
  return circumference * (1 - fillRatio);
};

export function ImpactCircles({ data, scope, compact = false }: ImpactCirclesProps) {
  return (
    // Use CSS custom property to drive all sizes from one fluid value.
    // clamp(min, preferred, max): on a 320px phone each orb ~26vw ≈ 84px;
    // on a 390px phone ~102px; on 430px+ capped at 148px (or 92px compact).
    <div
      className="flex justify-center items-start"
      style={{
        gap: "clamp(8px, 3vw, 20px)",
        // One CSS var drives orb diameter throughout the subtree
        ["--orb" as string]: compact
          ? "clamp(72px, 22vw, 96px)"
          : "clamp(84px, 26vw, 148px)",
      }}
    >
      {data.map((metric) => {
        const thisWeek   = metric.thisWeek[scope];
        const lastWeek   = metric.lastWeek[scope];
        const allTime    = metric.allTime[scope];
        const pct        = lastWeek > 0 ? ((thisWeek - lastWeek) / lastWeek) * 100 : 0;
        const changeInfo = getChangeInfo(pct);
        const config     = COLOR_CONFIG[metric.id] ?? COLOR_CONFIG.co2;
        const dashOffset = getRingDash(pct);

        let fullLabel = "";
        let descriptor = "";
        switch (metric.id) {
          case "co2": fullLabel = "Carbon Footprint Avoided"; descriptor = "CO₂eq this week";    break;
          case "gnh": fullLabel = "Happiness Index";          descriptor = "GNH domains";         break;
          case "cci": fullLabel = "Community Contribution";   descriptor = "care hrs × impact";   break;
        }

        return (
          <div
            key={metric.id}
            className="flex flex-col items-center"
            style={{ gap: "clamp(4px, 1.5vw, 10px)", flex: "1 1 0", minWidth: 0 }}
          >
            {/* Orb container — sized by --orb */}
            <div
              className="relative flex items-center justify-center"
              style={{ width: "var(--orb)", height: "var(--orb)" }}
            >
              {/* Outer glow */}
              <div
                className="absolute rounded-full blur-3xl animate-pulse"
                style={{
                  inset: "-20%",
                  backgroundColor: `${config.glowColor}26`,
                }}
              />
              {/* Inner glow */}
              <div
                className="absolute rounded-full blur-2xl"
                style={{
                  inset: "-10%",
                  backgroundColor: `${config.glowColor}40`,
                  animation: "pulse 3s ease-in-out infinite",
                }}
              />

              {/* Main orb — fills container */}
              <div
                className="relative w-full h-full flex items-center justify-center rounded-full shadow-2xl overflow-hidden"
                style={{
                  background: `linear-gradient(145deg, ${config.gradientFrom} 0%, ${config.gradientTo} 100%)`,
                }}
              >
                <div className="absolute inset-0 rounded-full bg-gradient-to-tr from-transparent via-white/5 to-white/10" />

                {/* Progress ring SVG */}
                <svg
                  viewBox="0 0 120 120"
                  className="absolute inset-0 w-full h-full"
                  aria-hidden="true"
                >
                  <circle cx="60" cy="60" r={svgRadius}
                    fill="none" stroke={changeInfo.ringColor}
                    strokeWidth="5" opacity="0.20"
                  />
                  <circle cx="60" cy="60" r={svgRadius}
                    fill="none" stroke={changeInfo.ringColor}
                    strokeWidth="5" strokeLinecap="round"
                    strokeDasharray={circumference}
                    strokeDashoffset={dashOffset}
                    style={{
                      transform: "rotate(-90deg)",
                      transformOrigin: "60px 60px",
                      filter: `drop-shadow(0 0 4px ${changeInfo.ringColor})`,
                    }}
                  />
                </svg>

                {/* Center text — fluid font sizes relative to orb */}
                <div className="relative z-10 flex flex-col items-center justify-center select-none px-1">
                  <span
                    className="font-semibold leading-none text-white"
                    style={{ fontSize: "clamp(14px, 5.5vw, 28px)" }}
                  >
                    {formatValue(allTime)}
                  </span>
                  {metric.unit && (
                    <span
                      className="font-medium text-white/90 leading-none"
                      style={{ fontSize: "clamp(9px, 2.5vw, 13px)", marginTop: "2px" }}
                    >
                      {metric.unit}
                    </span>
                  )}
                  <span
                    className="text-white/80 leading-tight text-center"
                    style={{ fontSize: "clamp(7px, 2vw, 10px)", marginTop: "4px" }}
                  >
                    {formatValue(thisWeek)} this wk
                  </span>
                </div>
              </div>

              {/* Floating particles */}
              <div className="pointer-events-none absolute inset-0">
                {[
                  { l: "35%", t: "42%", dur: "3s",   del: "0s"   },
                  { l: "58%", t: "38%", dur: "3.5s", del: "0.3s" },
                  { l: "45%", t: "55%", dur: "4s",   del: "0.6s" },
                  { l: "62%", t: "48%", dur: "4.5s", del: "0.9s" },
                  { l: "40%", t: "35%", dur: "5s",   del: "1.2s" },
                  { l: "52%", t: "60%", dur: "5.5s", del: "1.5s" },
                ].map((p, i) => (
                  <div
                    key={i}
                    className="absolute h-1 w-1 rounded-full"
                    style={{
                      left: p.l, top: p.t,
                      backgroundColor: config.particleColor,
                      animation: `orb-float ${p.dur} ease-in-out infinite ${p.del}`,
                    }}
                  />
                ))}
              </div>
            </div>

            {/* Labels */}
            <div className="text-center w-full px-1">
              <p
                className="font-medium text-foreground leading-tight"
                style={{ fontSize: "clamp(9px, 2.8vw, 13px)" }}
              >
                {fullLabel}
              </p>
              <p
                className="text-muted-foreground leading-tight"
                style={{ fontSize: "clamp(8px, 2.2vw, 11px)" }}
              >
                {descriptor}
              </p>
            </div>

            {/* Change badge */}
            <div
              className="flex items-center gap-0.5 font-medium"
              style={{ fontSize: "clamp(8px, 2.5vw, 11px)", color: changeInfo.labelColor }}
            >
              <span>{changeInfo.symbol}</span>
              <span>{changeInfo.label} vs last wk</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
