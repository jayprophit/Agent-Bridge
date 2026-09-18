import json, urllib.request

base = 'http://127.0.0.1:8472'

# Check selfcheck for allowed roots
try:
    with urllib.request.urlopen(base + '/v1/selfcheck', timeout=10) as resp:
        sc = json.loads(resp.read().decode())
    print('selfcheck checks passed')
    # Look at allowed_roots detail
    for check in sc.get('checks', []):
        if 'allowed_roots' in check.get('check', ''):
            print('allowed_roots check:', check)
except Exception as e:
    print('selfcheck error:', e)

# Check capabilities for workspace roots info
try:
    with urllib.request.urlopen(base + '/v1/capabilities', timeout=10) as resp:
        cap = json.loads(resp.read().decode())
    print('capabilities default_model:', cap.get('default_model'))
    print('capabilities approvals:', cap.get('approvals'))
    print('capabilities modes:', cap.get('modes'))
    print('capabilities presets:', cap.get('presets'))
except Exception as e:
    print('capabilities error:', e)