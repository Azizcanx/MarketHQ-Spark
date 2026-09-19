#!/usr/bin/env python3
import os, sys
lock = "/tmp/agentspace.lock"
if os.path.exists(lock):
    os.remove(lock)
    print("Stale lock removed")
else:
    print("No stale lock")