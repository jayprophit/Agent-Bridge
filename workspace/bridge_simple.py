import json, urllib.request, time, sys

sys.path.insert(0, r'C:\Users\jpowe\Desktop\IDE-Workspace\workspace')
sys.path.insert(0, r'C:\Users\jpowe\Desktop\Agent-Bridge')

from client import AgentRuntimeClient

base = 'http://127.0.0.1:8472'
cli = AgentRuntimeClient(base=base, token='')

# Create a fresh session
s = cli.create_session(
    workspace='.',
    mode='build',
    approval='AUTO_SAFE',
    model='hhao/qwen2.5-coder-tools:3b'
)
sid = s.get('session_id')
print('Session:', sid)

# Submit a VERY simple task: just create a file
task_text = "Create a file called test-hello.txt containing only the text 'Hello World'. Do not add any other content."
print('Task text:', task_text[:80])

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
    
    # Wait for completion with very short poll
    print('Waiting...')
    for i in range(12):  # 1 min max
        time.sleep(5)
        status_req = urllib.request.Request(base + '/v1/sessions/' + sid + '/status')
        with urllib.request.urlopen(status_req, timeout=15) as resp3:
            st = json.loads(resp3.read().decode())
            tasks = st.get('tasks', {})
            task_status = tasks.get(tid, '')
            print('  status:', task_status, end='\r')
            if task_status in ('COMPLETED', 'FAILED', 'CANCELLED', 'ROLLED_BACK', 'INTERRUPTED'):
                print()
                print('Final status:', task_status)
                # Get export
                try:
                    export_req = urllib.request.Request(base + '/v1/sessions/' + sid + '/export?task=' + tid + '&format=markdown')
                    with urllib.request.urlopen(export_req, timeout=15) as resp5:
                        exp = resp5.read().decode()
                        print('export:', exp[:1000])
                except Exception as e:
                    print('export error:', e)
                break
PYEOF