import type { UserProfile } from "../types";

export function getSpeedMultiplier(profile: UserProfile): number {
  const standardSpeedMps = 1.3;
  return Math.max(0.4, Math.min(1.2, (profile.walkingSpeedMps || 1) / standardSpeedMps));
}
