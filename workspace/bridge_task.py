import json, urllib.request, time, sys

sys.path.insert(0, r'C:\Users\jpowe\Desktop\IDE-Workspace\workspace')
sys.path.insert(0, r'C:\Users\jpowe\Desktop\Agent-Bridge')

from client import AgentRuntimeClient

base = 'http://127.0.0.1:8472'
cli = AgentRuntimeClient(base=base, token='')

# Submit a new task to the SAME session
sid = 's-deb5207e99'  # existing session from earlier

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
tdata = json.dumps({
    'text': task_text
}).encode()
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

    # Wait for task completion
    print('Waiting for task completion...')
    end = time.time() + 300  # 5 min timeout
    last_status = ''
    while time.time() < end:
        status_req = urllib.request.Request(base + '/v1/sessions/' + sid + '/status')
        with urllib.request.urlopen(status_req, timeout=15) as resp3:
            st = json.loads(resp3.read().decode())
            tasks = st.get('tasks', {})
            task_status = tasks.get(tid, '')
            print('  task {} status: {}'.format(tid, task_status), end='\r')
            if task_status in ('COMPLETED', 'FAILED', 'CANCELLED', 'ROLLED_BACK', 'INTERRUPTED'):
                last_status = task_status
                break
        time.sleep(5)

    print()
    print('Final task status:', last_status)

    # Get the full status
    print('Full session status:')
    print(json.dumps(st, indent=2)[:2000])

    # Check for files / exports
    print()
    print('Checking for task export/manifest...')

    # 1) manifest
    try:
        manifest_req = urllib.request.Request(base + '/v1/sessions/' + sid + '/manifest')
        with urllib.request.urlopen(manifest_req, timeout=15) as resp4:
            m = json.loads(resp4.read().decode())
            print('manifest:', json.dumps(m)[:2000])
    except Exception as e:
        print('manifest error:', e)

    # 2) export
    try:
        export_req = urllib.request.Request(base + '/v1/sessions/' + sid + '/export?task=' + tid + '&format=markdown')
        with urllib.request.urlopen(export_req, timeout=15) as resp5:
            exp = resp5.read().decode()
            print('export length:', len(exp))
            print('export preview:', exp[:500])
    except Exception as e:
        print('export error:', e)