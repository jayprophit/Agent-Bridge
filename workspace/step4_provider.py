import json, urllib.request, time, sys

sys.path.insert(0, r'C:\Users\jpowe\Desktop\IDE-Workspace\workspace')
sys.path.insert(0, r'C:\Users\jpowe\Desktop\Agent-Bridge')

from client import AgentRuntimeClient

base = 'http://127.0.0.1:8472'
cli = AgentRuntimeClient(base=base, token='')

# Test 1: health
print('Test 1 health:', cli.health())

# Test 2: models  
m = cli.models()
print('Test 2 models count:', len(m.get('models', [])))

# Test 3: capabilities
c = cli.capabilities()
print('Test 3 capabilities default_model:', c.get('default_model'))
print('Test 3 capabilities approvals:', c.get('approvals'))

# Test 4: create session with '.' workspace root (the allowed one)
print()
print('Test 4: create session with workspace=.')
s = cli.create_session(
    workspace='.',
    mode='build',
    approval='AUTO_SAFE',
    model='hhao/qwen2.5-coder-tools:3b'
)
print('  create_session result:', json.dumps(s)[:300])
sid = s.get('session_id')

if sid:
    # Test 5: submit a very simple task
    print()
    print('Test 5: submit simple task "Create hello.txt with HELLO"')
    tdata = json.dumps({
        'text': 'Create a file called hello.txt containing exactly HELLO.'
    }).encode()
    req = urllib.request.Request(
        base + '/v1/sessions/' + sid + '/tasks', 
        data=tdata, 
        method='POST', 
        headers={'Content-Type': 'application/json'}
    )
    with urllib.request.urlopen(req, timeout=30) as resp2:
        t = json.loads(resp2.read().decode())
        tid = t.get('task_id')
        print('  task_id:', tid)
        
        # Wait for completion with polling
        print('  Waiting for completion...')
        for i in range(20):  # 1 min max
            time.sleep(3)
            status_req = urllib.request.Request(base + '/v1/sessions/' + sid + '/status')
            with urllib.request.urlopen(status_req, timeout=15) as resp3:
                st = json.loads(resp3.read().decode())
                tasks = st.get('tasks', {})
                task_status = tasks.get(tid, '')
                if task_status in ('COMPLETED', 'FAILED', 'CANCELLED', 'ROLLED_BACK', 'INTERRUPTED'):
                    print('  final status after', (i+1)*3, 's:', task_status)
                    # Get export
                    try:
                        export_req = urllib.request.Request(base + '/v1/sessions/' + sid + '/export?task=' + tid + '&format=markdown')
                        with urllib.request.urlopen(export_req, timeout=15) as resp5:
                            exp = resp5.read().decode()
                            print('  export:', exp[:500])
                    except Exception as e:
                        print('  export error:', e)
                    break
PYEOF