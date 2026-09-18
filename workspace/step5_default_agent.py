import json, urllib.request, time, sys

sys.path.insert(0, r'C:\Users\jpowe\Desktop\IDE-Workspace\workspace')
sys.path.insert(0, r'C:\Users\jpowe\Desktop\Agent-Bridge')

from client import AgentRuntimeClient

base = 'http://127.0.0.1:8472'
cli = AgentRuntimeClient(base=base, token='')

# Use run_task which has built-in revision logic
print('=== DefaultAgent run_task test ===')
result = cli.run_task(
    session_id='s-a382b63d6c',  # fresh session
    text='Create a file called hello.txt containing exactly HELLO.',
    idempotency_key='test-hello-001'
)
print('run_task result:')
print(json.dumps(result)[:1000])

# Check if task completed
if result.get('task_id'):
    tid = result['task_id']
    # Check status
    try:
        status_req = urllib.request.Request(base + '/v1/sessions/s-a382b63d6c/status')
        with urllib.request.urlopen(status_req, timeout=15) as resp:
            st = json.loads(resp.read().decode())
            print('session tasks:', st.get('tasks'))
    except Exception as e:
        print('status error:', e)
PYEOF