#!/usr/bin/env python3
"""Real valid external workspace acceptance test."""
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, r'C:\Users\jpowe\Desktop\Agent-Bridge')

from runtime import AgentRuntime, RuntimeConfig

print("=" * 60)
print("REAL VALID EXTERNAL WORKSPACE ACCEPTANCE TEST")
print("=" * 60)

# Create temp directories
bridge_tmp = Path(tempfile.mkdtemp(prefix="v082_bridge_"))
ide_tmp = Path(tempfile.mkdtemp(prefix="v082_ide_"))
ide_workspace = ide_tmp / "proj"
ide_workspace.mkdir()

try:
    # Create runtime with external workspace as allowed root
    cfg = RuntimeConfig(allowed_workspace_roots=[str(ide_workspace)])
    runtime = AgentRuntime(cfg)
    
    # Create session with the exact external workspace
    session = runtime.create_session(str(ide_workspace), mode="build")
    print(f"Session created with workspace: {session.workspace}")
    print(f"Expected: {ide_workspace}")
    
    if str(session.workspace) != str(ide_workspace):
        print("FAIL: Workspace mismatch")
        sys.exit(1)
    print("WORKSPACE_PREFLIGHT = PASS")
    
    # Submit task: Create hello.txt containing exactly HELLO
    task_id = session.submit_task("Create a file hello.txt containing exactly HELLO")
    print(f"Task submitted: {task_id}")
    
    # Wait for completion
    for _ in range(30):
        time.sleep(2)
        status = runtime.task_status(task_id) if hasattr(runtime, 'task_status') else None
        if not status:
            # Try session task_status
            status = runtime.get_session(runtime.list_sessions()[0]["session_id"]).task_status(task_id)
        if status['status'] in ('COMPLETED', 'FAILED', 'CANCELLED'):
            break
    
    print(f"MODEL_PLANNING = {'PASS' if 'planning.started' in str(status) else 'UNKNOWN'}")
    print(f"Task status: {status['status']}")
    
    # Check file creation
    hello_file = ide_workspace / "hello.txt"
    if hello_file.exists():
        content = hello_file.read_text()
        print(f"FILE_ACTION = PASS (file created)")
        print(f"File content: '{content}'")
        if content.strip() == "HELLO":
            print("VERIFICATION = PASS (content verified)")
        else:
            print(f"VERIFICATION = FAIL (content mismatch: got '{content}')")
    else:
        print("FILE_ACTION = FAIL (file not created)")
        print("VERIFICATION = FAIL")
    
    # Check events
    # We need to get events from the session
    session_obj = runtime.get_session(runtime.list_sessions()[0]["session_id"])
    events = session_obj.events_since(0)
    event_kinds = {e.get('event', '') for e in events.get('events', [])}
    print(f"Events: {event_kinds}")
    
    # Summary
    workspace_preflight = "PASS"
    model_planning = "PASS" if 'planning.started' in str(event_kinds) else "FAIL"
    file_action = "PASS" if hello_file.exists() else "FAIL"
    verification = "PASS" if hello_file.exists() and hello_file.read_text().strip() == "HELLO" else "FAIL"
    end_to_end = "PASS" if all([workspace_preflight == "PASS", model_planning == "PASS", file_action == "PASS", verification == "PASS"]) else "PARTIAL"
    
    print("\n=== SUMMARY ===")
    print(f"WORKSPACE_PREFLIGHT = {workspace_preflight}")
    print(f"MODEL_PLANNING = {model_planning}")
    print(f"FILE_ACTION = {file_action}")
    print(f"VERIFICATION = {verification}")
    print(f"REAL_EXTERNAL_END_TO_END = {end_to_end}")

finally:
    import shutil
    shutil.rmtree(bridge_tmp, ignore_errors=True)
    shutil.rmtree(ide_tmp, ignore_errors=True)