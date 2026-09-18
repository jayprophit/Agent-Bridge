import json, urllib.request, time, sys

sys.path.insert(0, r'C:\Users\jpowe\Desktop\IDE-Workspace\workspace')
sys.path.insert(0, r'C:\Users\jpowe\Desktop\Agent-Bridge')

from client import AgentRuntimeClient

base = 'http://127.0.0.1:8472'
cli = AgentRuntimeClient(base=base, token='')

# Test 1: health
h = cli.health()
print('Test 1 health:', json.dumps(h)[:200])

# Test 2: models
m = cli.models()
print('Test 2 models count:', len(m.get('models', [])))

# Test 3: capabilities
c = cli.capabilities()
print('Test 3 capabilities default_model:', c.get('default_model'))

# Test 4: create session with '.' workspace root (the allowed one)
s = cli.create_session(
    workspace='.',
    mode='build',
    approval='AUTO_SAFE',
    model='hhao/qwen2.5-coder-tools:3b'
)
print('Test 4 create_session:', json.dumps(s)[:500])
sid = s.get('session_id')

if sid:
    # Test 5: submit task
    print()
    tdata = json.dumps({
        'text': 'Create a TypeScript utility called taskStatus.ts that models status states PENDING, RUNNING, WAITING_APPROVAL, FAILED, VERIFIED_COMPLETE with typed definitions, conversion function, terminal check, and automated tests'
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
        print('Test 5 task_id:', tid)
        # Test 6: get progress/status
        print()
        print('Test 6: get session status')
        status_req = urllib.request.Request(base + '/v1/sessions/' + sid + '/status')
        with urllib.request.urlopen(status_req, timeout=15) as resp3:
            st = json.loads(resp3.read().decode())
            print('session status tasks:', st.get('tasks'))
            print('pending_approvals:', st.get('pending_approvals'))
            # Test 7: get actions/events
            print()
            print('Test 7: get actions/events')
            events_req = urllib.request.Request(base + '/v1/sessions/' + sid + '/events?since=0')
            with urllib.request.urlopen(events_req, timeout=15) as resp4:
                ev = json.loads(resp4.read().decode())
                events = ev.get('events', [])
                print('events count:', len(events))
                for evt in events[:5]:
                    print('  evt:', json.dumps(evt)[:200])
else:
    print('Session created but no task_id returned - checking events anyway')
    try:
        ev_req = urllib.request.Request(base + '/v1/sessions/' + sid + '/events?since=0')
        with urllib.request.urlopen(ev_req, timeout=15) as resp:
            ev_data = json.loads(resp.read().decode())
            print('events:', json.dumps(ev_data)[:500])
    except Exception as e2:
        print('events error:', e2)