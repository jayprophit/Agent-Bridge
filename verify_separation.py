import os
import subprocess

# Check that Agent-Bridge and IDE-WORKSPACE are separate
from pathlib import Path
agent_bridge = str(Path(__file__).resolve().parent)
ide_workspace = str(Path.home() / "Desktop" / "IDE-WORKSPACE")

# Check agent bridge has bridge.ts reference
bridge_ts_path = os.path.join(agent_bridge, 'bridge.ts')
print(f"Agent-Bridge has bridge.ts: {os.path.exists(bridge_ts_path)}")

# Check ide workspace has bridge reference
ide_bridge_ts = os.path.join(ide_workspace, 'workspace', 'app', 'src', 'bridge.ts')
print(f"IDE-WORKSPACE has bridge.ts: {os.path.exists(ide_bridge_ts)}")

# Check git remote for agent bridge
result = subprocess.run(['git', 'remote', '-v'], capture_output=True, text=True, cwd=agent_bridge)
print(f"Agent-Bridge git remote: {result.stdout.strip()[:200]}")

# Check ide bridge.ts for hidden coupling and version compatibility
if os.path.exists(ide_bridge_ts):
    with open(ide_bridge_ts, 'r') as f:
        content = f.read()
    # Check for version pinning
    has_version_pin = 'v1.0.0' in content or '0.8.1' in content
    print(f"IDE bridge.ts has version pinning: {has_version_pin}")
    
    # Check for checkVersionCompatibility
    has_check = 'checkVersionCompatibility' in content
    print(f"IDE bridge.ts has checkVersionCompatibility: {has_check}")
    
    # Look for any hidden coupling patterns
    hidden_patterns = ['hidden', 'filesystem', 'secret path', 'c:\\\\users']
    for pattern in hidden_patterns:
        found = pattern.lower() in content.lower()
        print(f"IDE bridge.ts contains '{pattern}': {found}")