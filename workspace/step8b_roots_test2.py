import json, urllib.request, urllib.parse, subprocess, time, sys

# Start new bridge with --root pointing to IDE workspace
cmd = [
    sys.executable, r'C:\Users\jpowe\Desktop\Agent-Bridge\cli.py',
    '--root', r'C:\Users\jpowe\Desktop\IDE-Workspace\workspace',
    '--approval', 'AUTO_SAFE',
    '--preset', 'STANDARD',
    'serve', '--host', '127.0.0.1', '--port', '8474'
]
proc = subprocess.Popen(cmd, cwd=r'C:\Users\jpowe\Desktop\Agent-Bridge', 
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
time.sleep(3)

# Test SDK create_session with EXACT allowed root path
print('=== SDK create_session with exact allowed root path ===')
sys.path.insert(0, r'C:\Users\jpowe\Desktop\IDE-Workspace\workspace')
sys.path.insert(0, r'C:\Users\jpowe\Desktop\Agent-Bridge')
from client import AgentRuntimeClient

cli = AgentRuntimeClient(base='http://127.0.0.1:8474', token='')

# Use the exact allowed root path as workspace
s = cli.create_session(
    workspace=r'C:\Users\jpowe\Desktop\IDE-Workspace\workspace',  # exact match
    mode='build',
    approval='AUTO_SAFE',
    model='hhao/qwen2.5-coder-tools:3b'
)
print('create_session result:', json.dumps(s)[:300])
sid = s.get('session_id')

if sid:
    # Submit task
    print('=== Submit task ===')
    tdata = json.dumps({'text': 'Create a file called test.txt containing exactly HELLO.'}).encode()
    req = urllib.request.Request(
        'http://127.0.0.1:8474/v1/sessions/' + sid + '/tasks', 
        data=tdata, 
        method='POST', 
        headers={'Content-Type': 'application/json'}
    )
    with urllib.request.urlopen(req, timeout=30) as resp2:
        t = json.loads(resp2.read().decode())
        tid = t.get('task_id')
        print('task_id:', tid)
        
        # Wait for completion
        print('Waiting for completion...')
        for i in range(20):
            time.sleep(3)
            status_req = urllib.request.Request('http://127.0.0.1:8474/v1/sessions/' + sid + '/status')
            with urllib.request.urlopen(status_req, timeout=15) as resp3:
                st = json.loads(resp3.read().decode())
                tasks = st.get('tasks', {})
                task_status = tasks.get(tid, '')
                print('  status:', task_status, end='\r')
                if task_status in ('COMPLETED', 'FAILED', 'CANCELLED', 'ROLLED_BACK', 'INTERRUPTED'):
                    print()
                    print('final:', task_status)
                    try:
                        export_req = urllib.request.Request('http://127.0.0.1:8474/v1/sessions/' + sid + '/export?task=' + tid + '&format=markdown')
                        with urllib.request.urlopen(export_req, timeout=15) as resp5:
                            exp = resp5.read().decode()
                            print('export:', exp[:300])
                    except Exception as e:
                        print('export error:', e)
                    break

proc.terminate()