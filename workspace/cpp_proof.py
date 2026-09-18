import json, urllib.request, time, sys, subprocess

# Start Agent Bridge with correct --root
cmd = [sys.executable, r'C:\Users\jpowe\Desktop\Agent-Bridge\cli.py', 
       '--root', r'C:\Users\jpowe\Desktop\IDE-Workspace\workspace',
       '--approval', 'AUTO_SAFE', '--preset', 'STANDARD',
       'serve', '--host', '127.0.0.1', '--port', '9014']
proc = subprocess.Popen(cmd, cwd=r'C:\Users\jpowe\Desktop\Agent-Bridge', 
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
time.sleep(3)

# Test health
try:
    with urllib.request.urlopen('http://127.0.0.1:9014/health', timeout=5) as resp:
        print('Bridge on 9014 healthy:', resp.status)
except Exception as e:
    print('Bridge on 9014 error:', e)
    proc.terminate()
    sys.exit(1)

# Create session with exact workspace path
sys.path.insert(0, r'C:\Users\jpowe\Desktop\IDE-Workspace\workspace')
sys.path.insert(0, r'C:\Users\jpowe\Desktop\Agent-Bridge')
from client import AgentRuntimeClient

cli = AgentRuntimeClient(base='http://127.0.0.1:9014', token='')
s = cli.create_session(
    workspace=r'C:\Users\jpowe\Desktop\IDE-Workspace\workspace',
    mode='build',
    approval='AUTO_SAFE',
    model='hhao/qwen2.5-coder-tools:3b'
)
sid = s.get('session_id')
print('Session:', sid)

# Submit C++ task: Inventory class
task_text = 'Create a C++17 project called Inventory with header/source separation (Inventory.h / Inventory.cpp), implementing: add_item(name, quantity), remove_item(name), update_quantity(name, new_quantity), query_quantity(name), list_items(), reject negative quantities, preserve item names. Use strong types, clear error handling, and automated tests. Build with CMake + Ninja.'

print('Submitting C++ task to session', sid)
tdata = json.dumps({'text': task_text}).encode()
req = urllib.request.Request(
    'http://127.0.0.1:9014/v1/sessions/' + sid + '/tasks', 
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
    end = time.time() + 300  # 5 min timeout
    last_status = ''
    while time.time() < end:
        status_req = urllib.request.Request('http://127.0.0.1:9014/v1/sessions/' + sid + '/status')
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
        export_req = urllib.request.Request('http://127.0.0.1:9014/v1/sessions/' + sid + '/export?task=' + tid + '&format=markdown')
        with urllib.request.urlopen(export_req, timeout=15) as resp5:
            exp = resp5.read().decode()
            print('export length:', len(exp))
            print('export preview:', exp[:1500])
    except Exception as e:
        print('export error:', e)
    
    # Check events
    try:
        events_req = urllib.request.Request('http://127.0.0.1:9014/v1/sessions/' + sid + '/events?since=0')
        with urllib.request.urlopen(events_req, timeout=15) as resp4:
            ev = json.loads(resp4.read().decode())
            events = ev.get('events', [])
            print('events count:', len(events))
            for evt in events[:15]:
                print('  event:', json.dumps(evt)[:250])
    except Exception as e:
        print('events error:', e)

proc.terminate()
print('--- DONE ---')