import os, re
from pathlib import Path

reporoot = str(Path(__file__).resolve().parent)
found = False
for root, dirs, files in os.walk(reporoot):
    for f in files:
        if f.endswith('.py'):
            try:
                fpath = os.path.join(root, f)
                with open(fpath, 'r', errors='replace') as fh:
                    content = fh.read()
                    if 'jpowe' in content:
                        print(f'{fpath}: contains personal path')
                        found = True
            except Exception as e:
                pass
if not found:
    print('No personal paths found in .py files')