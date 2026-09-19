import assert from "node:assert/strict";
import { acquireAutonomousCycleLock, isAutonomousCycleLocked, releaseAutonomousCycleLock } from "./autonomous-cycle-lock";

assert.equal(acquireAutonomousCycleLock("cycle-1"), true);
assert.equal(isAutonomousCycleLocked("cycle-1"), true);
assert.equal(acquireAutonomousCycleLock("cycle-1"), false);
assert.equal(acquireAutonomousCycleLock("cycle-2"), true);
releaseAutonomousCycleLock("cycle-1");
assert.equal(isAutonomousCycleLocked("cycle-1"), false);
assert.equal(acquireAutonomousCycleLock("cycle-1"), true);
releaseAutonomousCycleLock("cycle-1");
releaseAutonomousCycleLock("cycle-2");

console.log("AUTONOMOUS_CYCLE_LOCK_TESTS PASS");
