const activeCycles = new Set<string>();

export function acquireAutonomousCycleLock(cycleId: string): boolean {
  const key = cycleId.trim();
  if (!key || activeCycles.has(key)) return false;
  activeCycles.add(key);
  return true;
}

export function releaseAutonomousCycleLock(cycleId: string): void {
  const key = cycleId.trim();
  if (key) activeCycles.delete(key);
}

export function isAutonomousCycleLocked(cycleId: string): boolean {
  return activeCycles.has(cycleId.trim());
}
