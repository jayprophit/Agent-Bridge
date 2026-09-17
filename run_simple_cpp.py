#!/usr/bin/env python3
import json, urllib.request, time, sys, subprocess

# Start Agent Bridge with correct workspace root
bridge_cmd = [sys.executable, r'C:\Users\jpowe\Desktop\Agent-Bridge\cli.py', 
              '--root', r'C:\Users\jpowe\Desktop\IDE-Workspace\workspace',
              '--approval', 'AUTO_SAFE', '--preset', 'STANDARD',
              'serve', '--host', '127.0.0.1', '--port', '9022']
proc = subprocess.Popen(bridge_cmd, cwd=r'C:\Users\jpowe\Desktop\Agent-Bridge',
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

# Wait for bridge to be healthy
for i in range(10):
    time.sleep(2)
    try:
        with urllib.request.urlopen('http://127.0.0.1:9022/health', timeout=5) as resp:
            health = resp.read().decode()
            print('Bridge healthy on 9022:', health[:100])
            break
    except Exception as e:
        print('Waiting for bridge...', e)
else:
    print('Bridge not healthy after 20s'); proc.terminate(); import sys; sys.exit(1)

# Create session and submit simple C++ task
sys.path.insert(0, r'C:\Users\jpowe\Desktop\IDE-Workspace\workspace')
sys.path.insert(0, r'C:\Users\jpowe\Desktop\Agent-Bridge')
from client import AgentRuntimeClient
cli = AgentRuntimeClient(base='http://127.0.0.1:9022', token='')
s = cli.create_session(
    workspace=r'C:\Users\jpowe\Desktop\IDE-Workspace\workspace',
    mode='build',
    approval='AUTO_SAFE',
    model='hhao/qwen2.5-coder-tools:3b'
)
sid = s.get('session_id')
print('Session:', sid)

# Submit simple C++ "Hello World" task
task_text = 'Create a simple C++ program that prints "HELLO" to stdout and creates a file test.txt containing exactly HELLO. Use clang++ to compile. Submit COMPLETED task with FILES: PASS.'
tdata = json.dumps({'text': task_text}).encode()
req = urllib.request.Request(
    'http://127.0.0.1:9022/v1/sessions/' + sid + '/tasks', 
    data=tdata, 
    method='POST', 
    headers={'Content-Type': 'application/json'}
)
with urllib.request.urlopen(req, timeout=30) as resp2:
    result = json.loads(resp2.read().decode())
    tid = result.get('task_id')
    print('task_id:', tid)
    
    # Wait for completion
    for i in range(30):
        time.sleep(3)
        try:
            status_req = urllib.request.Request('http://127.0.0.1:9022/v1/sessions/' + sid + '/status')
            with urllib.request.urlopen(status_req, timeout=10) as sresp:
                st = json.loads(sresp.read().decode())
                task_status = st.get('tasks', {}).get(tid, '')
                print('status after', (i+1)*3, 's:', task_status)
                if task_status in ('COMPLETED', 'FAILED', 'CANCELLED', 'ROLLED_BACK', 'INTERRUPTED'):
                    print('FINAL STATUS:', task_status)
                    break
        except Exception as e:
            print('status error:', e)
    
    # Get export
    try:
        export_req = urllib.request.Request('http://127.0.0.1:9022/v1/sessions/' + sid + '/export')
        with urllib.request.urlopen(export_req, timeout=15) as xresp:
            export = json.loads(xresp.read().decode())
            print('export:', json.dumps(export)[:500])
    except Exception as e:
        print('export error:', e)

proc.terminate()
print('DONE')