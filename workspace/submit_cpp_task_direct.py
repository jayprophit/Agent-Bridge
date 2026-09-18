"""Submit a C++ inventory task through Agent Bridge to hhao/qwen2.5-coder-tools:3b."""
import json, urllib.request, time, sys

sys.path.insert(0, r'C:\Users\jpowe\Desktop\IDE-Workspace\workspace')
sys.path.insert(0, r'C:\Users\jpowe\Desktop\Agent-Bridge')

from client import AgentRuntimeClient

base = 'http://127.0.0.1:9001'
cli = AgentRuntimeClient(base=base, token='')

# Create a fresh session
s = cli.create_session(
    workspace=r'C:\Users\jpowe\Desktop\IDE-Workspace\workspace',
    mode='build',
    approval='AUTO_SAFE',
    model='hhao/qwen2.5-coder-tools:3b'
)
sid = s.get('session_id')
print('Session:', sid)

# Submit the C++ task
task_text = "Create a C++17 project called Inventory implementing an Inventory class.\n\nRequired operations:\n- add item (name, quantity)\n- remove item (name)\n- update quantity (name, new_quantity)\n- query quantity (name)\n- list items\n- reject negative quantities\n- preserve item names\n\nUse:\n- header/source separation (Inventory.h / Inventory.cpp)\n- strong types where sensible\n- clear error handling\n- automated tests\n\nThe project should be buildable with CMake + Ninja using the detected toolchain.\nCompile and run the tests to verify."

print('Submitting C++ task to session', sid)
tdata = json.dumps({'text': task_text}).encode()
req = urllib.request.Request(
    base + '/v1/sessions/' + sid + '/tasks', 
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
        status_req = urllib.request.Request(base + '/v1/sessions/' + sid + '/status')
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
        export_req = urllib.request.Request(base + '/v1/sessions/' + sid + '/export?task=' + tid + '&format=markdown')
        with urllib.request.urlopen(export_req, timeout=15) as resp5:
            exp = resp5.read().decode()
            print('export length:', len(exp))
            print('export preview:', exp[:1500])
    except Exception as e:
        print('export error:', e)
    
    # Check events
    try:
        events_req = urllib.request.Request(base + '/v1/sessions/' + sid + '/events?since=0')
        with urllib.request.urlopen(events_req, timeout=15) as resp4:
            ev = json.loads(resp4.read().decode())
            events = ev.get('events', [])
            print('events count:', len(events))
            for evt in events[:10]:
                print('  event:', json.dumps(evt)[:200])
    except Exception as e:
        print('events error:', e)
" 2>&1