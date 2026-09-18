import json, urllib.request, urllib.parse, subprocess, time, sys

# Start new bridge with --root pointing to IDE workspace
cmd = [
    sys.executable, r'C:\Users\jpowe\Desktop\Agent-Bridge\cli.py',
    '--root', r'C:\Users\jpowe\Desktop\IDE-Workspace\workspace',
    '--approval', 'AUTO_SAFE',
    '--preset', 'STANDARD',
    'serve', '--host', '127.0.0.1', '--port', '8473'
]
proc = subprocess.Popen(cmd, cwd=r'C:\Users\jpowe\Desktop\Agent-Bridge', 
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
time.sleep(3)

# Test health
try:
    with urllib.request.urlopen('http://127.0.0.1:8473/health', timeout=5) as resp:
        print('Bridge on 8473 healthy')
except Exception as e:
    print('Bridge on 8473 error:', e)
    proc.terminate()
    sys.exit(1)

# Test workspace with '.'
print('=== Test workspace=. ===')
try:
    url = 'http://127.0.0.1:8473/v1/sessions?status=&workspace=' + urllib.parse.quote('.')
    with urllib.request.urlopen(url, timeout=15) as resp:
        s = json.loads(resp.read().decode())
        sessions = s.get('sessions', [])
        for sess in sessions[:3]:
            print('  session:', sess.get('session_id'), 'workspace:', sess.get('workspace'), 'status:', sess.get('status'))
except Exception as e:
    print('error:', e)

# Test workspace with full IDE path
print('=== Test workspace=IDE path ===')
try:
    url = 'http://127.0.0.1:8473/v1/sessions?status=&workspace=' + urllib.parse.quote(r'C:\Users\jpowe\Desktop\IDE-Workspace\workspace')
    with urllib.request.urlopen(url, timeout=15) as resp:
        s = json.loads(resp.read().decode())
        sessions = s.get('sessions', [])
        for sess in sessions[:3]:
            print('  session:', sess.get('session_id'), 'workspace:', sess.get('workspace'), 'status:', sess.get('status'))
except Exception as e:
    print('error:', e)

# Test with no workspace filter
print('=== Test no workspace filter ===')
try:
    with urllib.request.urlopen('http://127.0.0.1:8473/v1/sessions?status=', timeout=15) as resp:
        s = json.loads(resp.read().decode())
        sessions = s.get('sessions', [])
        for sess in sessions[:3]:
            print('  session:', sess.get('session_id'), 'workspace:', sess.get('workspace'), 'status:', sess.get('status'))
except Exception as e:
    print('error:', e)

# Now test creating a session and submitting a task through the SDK
print('=== Test SDK create_session ===')
sys.path.insert(0, r'C:\Users\jpowe\Desktop\IDE-Workspace\workspace')
sys.path.insert(0, r'C:\Users\jpowe\Desktop\Agent-Bridge')
from client import AgentRuntimeClient

cli = AgentRuntimeClient(base='http://127.0.0.1:8473', token='')

s = cli.create_session(
    workspace='.',
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
        'http://127.0.0.1:8473/v1/sessions/' + sid + '/tasks', 
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
        for i in range(12):
            time.sleep(3)
            status_req = urllib.request.Request('http://127.0.0.1:8473/v1/sessions/' + sid + '/status')
            with urllib.request.urlopen(status_req, timeout=15) as resp3:
                st = json.loads(resp3.read().decode())
                tasks = st.get('tasks', {})
                task_status = tasks.get(tid, '')
                print('  status:', task_status, end='\r')
                if task_status in ('COMPLETED', 'FAILED', 'CANCELLED', 'ROLLED_BACK', 'INTERRUPTED'):
                    print()
                    print('final:', task_status)
                    try:
                        export_req = urllib.request.Request('http://127.0.0.1:8473/v1/sessions/' + sid + '/export?task=' + tid + '&format=markdown')
                        with urllib.request.urlopen(export_req, timeout=15) as resp5:
                            exp = resp5.read().decode()
                            print('export:', exp[:300])
                    except Exception as e:
                        print('export error:', e)
                    break

proc.terminate()