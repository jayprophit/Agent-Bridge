import json, urllib.request, time, sys, subprocess

# Start fresh bridge
cmd = [sys.executable, r'C:\Users\jpowe\Desktop\Agent-Bridge\cli.py', '--root', r'C:\Users\jpowe\Desktop\IDE-Workspace\workspace', '--approval', 'AUTO_SAFE', '--preset', 'STANDARD', 'serve', '--host', '127.0.0.1', '--port', '9011']
proc = subprocess.Popen(cmd, cwd=r'C:\Users\jpowe\Desktop\Agent-Bridge', stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
time.sleep(3)

# Test health
healthy = False
try:
    with urllib.request.urlopen('http://127.0.0.1:9011/health', timeout=5) as resp:
        healthy = resp.status == 200
    print('Bridge healthy:', healthy)
except Exception as e:
    print('Bridge healthy error:', e)

if not healthy:
    proc.terminate()
    sys.exit(1)

# Create session with exact allowed root path
sys.path.insert(0, r'C:\Users\jpowe\Desktop\IDE-Workspace\workspace')
sys.path.insert(0, r'C:\Users\jpowe\Desktop\Agent-Bridge')
from client import AgentRuntimeClient

cli = AgentRuntimeClient(base='http://127.0.0.1:9011', token='')
s = cli.create_session(
    workspace=r'C:\Users\jpowe\Desktop\IDE-Workspace\workspace',
    mode='build',
    approval='AUTO_SAFE',
    model='hhao/qwen2.5-coder-tools:3b'
)
sid = s.get('session_id')
print('Session:', sid)

# Submit minimal task: Create hello.txt with HELLO
task_text = 'Create a file called hello.txt containing exactly HELLO.'
print('Task text:', task_text[:60])
tdata = json.dumps({'text': task_text}).encode()
req = urllib.request.Request(
    'http://127.0.0.1:9011/v1/sessions/' + sid + '/tasks', 
    data=tdata, 
    method='POST', 
    headers={'Content-Type': 'application/json'}
)
with urllib.request.urlopen(req, timeout=30) as resp2:
    result = json.loads(resp2.read().decode())
    tid = result.get('task_id')
    print('task_id:', tid)
    
    # Wait and check status
    for i in range(12):
        time.sleep(3)
        status_req = urllib.request.Request('http://127.0.0.1:9011/v1/sessions/' + sid + '/status')
        with urllib.request.urlopen(status_req, timeout=15) as resp3:
            st = json.loads(resp3.read().decode())
            tasks = st.get('tasks', {})
            task_status = tasks.get(tid, '')
            print('status after', (i+1)*3, 's:', task_status, end='\r')
            if task_status in ('COMPLETED', 'FAILED', 'CANCELLED', 'ROLLED_BACK', 'INTERRUPTED'):
                print()
                print('final:', task_status)
                # Get export
                try:
                    export_req = urllib.request.Request('http://127.0.0.1:9011/v1/sessions/' + sid + '/export?task=' + tid + '&format=markdown')
                    with urllib.request.urlopen(export_req, timeout=15) as resp5:
                        exp = resp5.read().decode()
                        print('export:', exp[:500])
                except Exception as e:
                    print('export error:', e)
                break
    else:
        print('timeout - still running')
    
    # Get events
    try:
        events_req = urllib.request.Request('http://127.0.0.1:9011/v1/sessions/' + sid + '/events?since=0')
        with urllib.request.urlopen(events_req, timeout=15) as resp4:
            ev = json.loads(resp4.read().decode())
            events = ev.get('events', [])
            print('events count:', len(events))
            for evt in events:
                print('  event:', json.dumps(evt)[:200])
    except Exception as e:
        print('events error:', e)

proc.terminate()
print('--- DONE ---')