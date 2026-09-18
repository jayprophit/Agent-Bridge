import json, urllib.request, urllib.parse

base = 'http://127.0.0.1:8472'

# Test various workspace root values
test_roots = [
    '.',
    'C:\\\\Users\\\\jpowe\\\\Desktop\\\\IDE-Workspace\\\\workspace',
    'C:\\\\Users\\\\jpowe\\\\Desktop\\\\Agent-Bridge',
    './workspace',
    '.\\\\workspace',
    'workspace',
]

for root in test_roots:
    print(f'=== Testing workspace root: {root} ===')
    try:
        url = base + '/v1/sessions?status=&workspace=' + urllib.parse.quote(root)
        with urllib.request.urlopen(url, timeout=10) as resp:
            s = json.loads(resp.read().decode())
            sessions = s.get('sessions', [])
            if sessions:
                for sess in sessions[:2]:  # show first 2
                    print(f'  session: {sess.get("session_id")}, workspace={sess.get("workspace")}, status={sess.get("status")}')
            else:
                print('  no sessions created')
    except Exception as e:
        print(f'  error: {e}')
    print()
PYEOF