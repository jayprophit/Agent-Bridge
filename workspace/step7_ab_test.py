import json, urllib.request, time, sys

sys.path.insert(0, r'C:\Users\jpowe\Desktop\IDE-Workspace\workspace')
sys.path.insert(0, r'C:\Users\jpowe\Desktop\Agent-Bridge')

from client import AgentRuntimeClient

base = 'http://127.0.0.1:8472'
cli = AgentRuntimeClient(base=base, token='')

# Get available models from Agent Bridge
models_resp = cli.models()
available = m.get('models', []) if (m := models_resp) else []

# Filter to installed candidates
candidates = []
for m in available:
    name = m.get('name', '')
    if any(x in name for x in ['qwen2.5-coder', 'qwen3.5', 'granite3.3']):
        candidates.append(name)

print('Candidate models for A/B test:', candidates)

# Test each candidate with the simple task
task_text = 'Create a file called test.txt containing exactly HELLO.'

for model_name in candidates:
    print()
    print('='*60)
    print(f'Testing model: {model_name}')
    print('='*60)
    
    # Create fresh session
    s = cli.create_session(
        workspace='.',
        mode='build',
        approval='AUTO_SAFE',
        model=model_name
    )
    sid = s.get('session_id')
    print('  session_id:', sid)
    
    if sid:
        # Submit task
        tdata = json.dumps({'text': task_text}).encode()
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
            
            # Wait for completion
            print('  Waiting...')
            for i in range(12):
                time.sleep(3)
                status_req = urllib.request.Request(base + '/v1/sessions/' + sid + '/status')
                with urllib.request.urlopen(status_req, timeout=15) as resp3:
                    st = json.loads(resp3.read().decode())
                    tasks = st.get('tasks', {})
                    task_status = tasks.get(tid, '')
                    print('  status after', (i+1)*3, 's:', task_status, end='\r')
                    if task_status in ('COMPLETED', 'FAILED', 'CANCELLED', 'ROLLED_BACK', 'INTERRUPTED'):
                        print()
                        print('  final:', task_status)
                        try:
                            export_req = urllib.request.Request(base + '/v1/sessions/' + sid + '/export?task=' + tid + '&format=markdown')
                            with urllib.request.urlopen(export_req, timeout=15) as resp4:
                                exp = resp4.read().decode()
                                print('  export preview:', exp[:300])
                        except Exception as e:
                            print('  export error:', e)
                        break
PYEOF