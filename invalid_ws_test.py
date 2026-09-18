#!/usr/bin/env python3
"""Real invalid workspace acceptance test."""
import sys
import tempfile
import os
from pathlib import Path

sys.path.insert(0, r'C:\Users\jpowe\Desktop\Agent-Bridge')

from runtime import AgentRuntime, RuntimeConfig

print("=" * 60)
print("REAL INVALID WORKSPACE ACCEPTANCE TEST")
print("=" * 60)

# Create temp directories
bridge_tmp = Path(tempfile.mkdtemp(prefix="v082_bridge_"))
ide_tmp = Path(tempfile.mkdtemp(prefix="v082_ide_"))
ide_workspace = ide_tmp / "proj"
ide_workspace.mkdir()

try:
    # Create runtime with ONLY the external IDE workspace as allowed root
    # Bridge repo is NOT in allowed roots
    cfg = RuntimeConfig(allowed_workspace_roots=[str(ide_workspace)])
    runtime = AgentRuntime(cfg)
    
    # Create session with '.' - this should resolve to the allowed root (ide_workspace)
    # NOT the Bridge repo
    session = runtime.create_session(".", mode="build")
    print(f"Session created with workspace: {session.workspace}")
    print(f"Expected: {ide_workspace}")
    
    # Verify the workspace is the external IDE workspace, NOT the Bridge repo
    if str(session.workspace) == str(ide_workspace):
        print("PASS: '.' resolved to allowed root (external IDE workspace)")
    else:
        print(f"FAIL: Expected {ide_workspace}, got {session.workspace}")
        sys.exit(1)
    
    # Now submit a task with this session - should fail at PREFLIGHT if workspace was invalid
    # But since '.' resolved correctly, it should proceed to planning
    task_id = session.submit_task("Create test.txt containing HELLO")
    print(f"Task submitted: {task_id}")
    
    # Wait a bit and check status
    import time
    time.sleep(3)
    
    # Check events - should NOT have planning.started if preflight failed
    events = session.events_since(0)
    event_kinds = {e.get('event', '') for e in events.get('events', [])}
    print(f"Events: {event_kinds}")
    
    if 'planning.started' in event_kinds:
        print("planning.started was emitted - task proceeded to planning (expected for valid workspace)")
    else:
        print("planning.started NOT emitted - task failed at PREFLIGHT (unexpected for valid workspace)")
    
    # Test 2: Try workspace outside allowed roots
    print("\n--- Test 2: Workspace outside allowed roots ---")
    outside = bridge_tmp / "outside_allowed"
    outside.mkdir()
    
    try:
        session2 = runtime.create_session(str(outside), mode="build")
        print("FAIL: Should have rejected workspace outside allowed roots")
        sys.exit(1)
    except PermissionError as e:
        print(f"PASS: Correctly rejected workspace outside allowed roots: {e}")
    
    print("\n=== INVALID WORKSPACE ACCEPTANCE: PASS ===")

finally:
    import shutil
    shutil.rmtree(bridge_tmp, ignore_errors=True)
    shutil.rmtree(ide_tmp, ignore_errors=True)