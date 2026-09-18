import json, urllib.request

sid = 's-deb5207e99'
base = 'http://127.0.0.1:8472'

# Get events for the session
try:
    events_req = base + '/v1/sessions/' + sid + '/events?since=0'
    with urllib.request.urlopen(events_req, timeout=15) as resp:
        ev_data = json.loads(resp.read().decode())
        events = ev_data.get('events', [])
        print('All events for session:')
        for evt in events:
            print('  ', json.dumps(evt)[:200])
except Exception as e:
    print('events error:', e)