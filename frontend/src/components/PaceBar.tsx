import React from "react";

interface PaceBarProps {
  speedFactor: number;
}

export function PaceBar({ speedFactor }: PaceBarProps) {
  // speedFactor: 1.0 = normal, < 1.0 = slower, > 1.0 = faster
  // Render 10 subtle beating bars with height and delay variations based on walking speed
  const bars = Array.from({ length: 10 });

  return (
    <div className="flex items-end gap-[3px] h-[20px] select-none" aria-label="보행 속도 박자 바">
      {bars.map((_, i) => {
        // dynamic height based on index and speed multiplier
        const baseH = 6 + (i % 3 === 0 ? 10 : 5) * speedFactor;
        const barHeight = Math.max(5, Math.min(20, baseH));
        const delay = `${i * 0.07}s`;

        return (
          <span
            key={i}
            className="pace-bar-span block w-[3px] bg-[#E8863A] rounded-[2px]"
            style={{
              height: `${barHeight}px`,
              animationDelay: delay,
            }}
          />
        );
      })}
    </div>
  );
}
