import json, urllib.request

base = 'http://127.0.0.1:8472'

# Check what happens with explicit workspace root paths
# Test 1: using '.' (current working)
print('=== Test 1: workspace=.' )
try:
    with urllib.request.urlopen(base + '/v1/sessions?status=&workspace=' + urllib.parse.quote('.') , timeout=15) as resp:
        s = json.loads(resp.read().decode())
        print('sessions with .:', s)
except Exception as e:
    print('error with .:', e)

import urllib.parse

# Test 2: using the full IDE workspace path
print('=== Test 2: workspace=C:\\\\Users\\\\jpowe\\\\Desktop\\\\IDE-Workspace\\\\workspace' )
try:
    url = base + '/v1/sessions?status=&workspace=' + urllib.parse.quote(r'C:\Users\jpowe\Desktop\IDE-Workspace\workspace')
    with urllib.request.urlopen(url, timeout=15) as resp:
        s = json.loads(resp.read().decode())
        print('sessions with full path:', s)
except Exception as e:
    print('error with full path:', e)

# Test 3: no workspace filter
print('=== Test 3: no workspace filter ===')
try:
    with urllib.request.urlopen(base + '/v1/sessions?status=', timeout=15) as resp:
        s = json.loads(resp.read().decode())
        print('sessions no filter:', s)
except Exception as e:
    print('error no filter:', e)
PYEOF