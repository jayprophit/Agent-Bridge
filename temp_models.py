import json, urllib.request
try:
    data = urllib.request.urlopen('http://127.0.0.1:11434/api/tags').read()
    models = json.loads(data).get('models', [])
    print('Currently installed:')
    for m in models:
        print('  ' + m['name'])
except Exception as e:
    print('Error: ' + str(e))
PYEOF