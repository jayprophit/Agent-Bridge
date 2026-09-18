import json, urllib.request, time, sys

sys.path.insert(0, r'C:\Users\jpowe\Desktop\IDE-Workspace\workspace')
sys.path.insert(0, r'C:\Users\jpowe\Desktop\Agent-Bridge')

from client import AgentRuntimeClient

base = 'http://127.0.0.1:8474'  # Will be overridden by SDK config
cli = AgentRuntimeClient(base='http://127.0.0.1:8471', token='')

# Actually, let me use the bridge_service to start with correct root
# For now, let me manually start the bridge with correct root
import subprocess, time

cmd = [
    sys.executable, r'C:\Users\jpowe\Desktop\Agent-Bridge\cli.py',
    '--root', r'C:\Users\jpowe\Desktop\IDE-Workspace\workspace',
    '--approval', 'AUTO_SAFE',
    '--preset', 'STANDARD',
    'serve', '--host', '127.0.0.1', '--port', '8475'
]
proc = subprocess.Popen(cmd, cwd=r'C:\Users\jpowe\Desktop\Agent-Bridge', 
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
time.sleep(3)

# Test create_session with workspace = allowed root
cli2 = AgentRuntimeClient(base='http://127.0.0.1:8475', token='')
s = cli2.create_session(
    workspace=r'C:\Users\jpowe\Desktop\IDE-Workspace\workspace',
    mode='build',
    approval='AUTO_SAFE',
    model='hhao/qwen2.5-coder-tools:3b'
)
print('session_id:', s.get('session_id'))
sid = s.get('session_id')

if sid:
    # Submit the Qwen task
    task_text = """Create a TypeScript utility called taskStatus.ts that models:

PENDING
RUNNING
WAITING_APPROVAL
FAILED
VERIFIED_COMPLETE

Provide:
1. strongly typed status definitions
2. a function that converts a status to a user-facing label
3. a function that determines whether the task is terminal
4. automated tests
5. run the tests
6. repair any failure
7. finish only after verification."""
    
    print('Submitting task to session', sid)
    tdata = json.dumps({'text': task_text}).encode()
    req = urllib.request.Request(
        'http://127.0.0.1:8475/v1/sessions/' + sid + '/tasks', 
        data=tdata, 
        method='POST', 
        headers={'Content-Type': 'application/json'}
    )
    with urllib.request.urlopen(req, timeout=30) as resp2:
        result = json.loads(resp2.read().decode())
        tid = result.get('task_id')
        print('task_id:', tid)
        
        # Wait for completion
        print('Waiting for completion...')
        end = time.time() + 300
        last_status = ''
        while time.time() < end:
            status_req = urllib.request.Request('http://127.0.0.1:8475/v1/sessions/' + sid + '/status')
            with urllib.request.urlopen(status_req, timeout=15) as resp3:
                st = json.loads(resp3.read().decode())
                tasks = st.get('tasks', {})
                task_status = tasks.get(tid, '')
                print('  status:', task_status, end='\r')
                if task_status in ('COMPLETED', 'FAILED', 'CANCELLED', 'ROLLED_BACK', 'INTERRUPTED'):
                    last_status = task_status
                    break
            time.sleep(5)
        
        print()
        print('Final task status:', last_status)
        
        # Get export
        try:
            export_req = urllib.request.Request('http://127.0.0.1:8475/v1/sessions/' + sid + '/export?task=' + tid + '&format=markdown')
            with urllib.request.urlopen(export_req, timeout=15) as resp5:
                exp = resp5.read().decode()
                print('export length:', len(exp))
                print('export preview:', exp[:1000])
        except Exception as e:
            print('export error:', e)

proc.terminate()