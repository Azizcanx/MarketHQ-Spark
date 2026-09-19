import type { AutonomousCycleState } from "./autonomous-cycle-state";
import { getAutonomousCycleStore } from "./autonomous-cycle-store";

export type AutonomousCycleLease = {
  cycleId: string;
  ownerId: string;
  expiresAt: string;
};

const leases = new Map<string, AutonomousCycleLease>();

function now(): number { return Date.now(); }

export function acquireAutonomousCycleLease(cycleId: string, ownerId: string, ttlMs = 60_000): AutonomousCycleLease | null {
  if (!cycleId || !ownerId || !Number.isFinite(ttlMs) || ttlMs <= 0) return null;
  const current = leases.get(cycleId);
  if (current && Date.parse(current.expiresAt) > now() && current.ownerId !== ownerId) return null;
  const state = getAutonomousCycleStore().get(cycleId) as AutonomousCycleState | null;
  if (state && ["ACCEPTED", "REVIEW_REQUIRED", "FAILED", "BUDGET_EXCEEDED"].includes(state.status)) return null;
  const lease = { cycleId, ownerId, expiresAt: new Date(now() + ttlMs).toISOString() };
  leases.set(cycleId, lease);
  return lease;
}

export function releaseAutonomousCycleLease(cycleId: string, ownerId: string): boolean {
  const current = leases.get(cycleId);
  if (!current || current.ownerId !== ownerId) return false;
  leases.delete(cycleId);
  return true;
}

export function getAutonomousCycleLease(cycleId: string): AutonomousCycleLease | null {
  const current = leases.get(cycleId) ?? null;
  if (!current) return null;
  if (Date.parse(current.expiresAt) <= now()) { leases.delete(cycleId); return null; }
  return current;
}
