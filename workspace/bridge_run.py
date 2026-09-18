import json, urllib.request, time, sys

sys.path.insert(0, r'C:\Users\jpowe\Desktop\IDE-Workspace\workspace')
sys.path.insert(0, r'C:\Users\jpowe\Desktop\Agent-Bridge')

from client import AgentRuntimeClient

base = 'http://127.0.0.1:8472'
cli = AgentRuntimeClient(base=base, token='')

# Use run_task which does submit + wait + poll
print('=== run_task test ===')
result = cli.run_task(
    session_id='s-deb5207e99',
    text='Create a TypeScript file that exports a constant hello = "world". Just a single line.',
    idempotency_key='test-1'
)
print('run_task result:', json.dumps(result)[:1000])