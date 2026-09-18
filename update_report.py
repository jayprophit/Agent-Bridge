with open(r'C:\Users\jpowe\Desktop\IDE-Workspace\FINAL_REPORT.md', 'r') as f:
    content = f.read()

old_marker = 'Qwen authored files: YES (after configuration fix)'
new_marker = 'Qwen authored files: **YES** (with correct workspace configuration)'

idx = content.find(old_marker)
if idx >= 0:
    # Found the start of the section to replace - locate the end
    end_marker = 'repair loop: NOT REQUIRED'
    idx2 = content.find(end_marker, idx)
    if idx2 >= 0:
        new_section = '''35. FAILED
==================================================
- Qwen task execution through Agent Bridge: 3/3 tasks FAILED **with \`workspace='.'\`** (root cause: workspace configuration)
  - Cause: WORKSPACE_CONFIGURATION — \`workspace='.'\` resolved to Agent Bridge directory, not IDE workspace
  - Fix applied: Agent Bridge started with \`--root C:\\Users\\jpowe\\Desktop\\IDE-Workspace\\workspace\`, SDK uses \`workspace=C:\\Users\\jpowe\\Desktop\\IDE-Workspace\\workspace\`
  - After fix: Tasks COMPLETE successfully with "FILES: PASS — 1 file(s) changed with verification" (see sections 13, 14)
  - Previously: Tasks FAILED after planning.started within ~0.3s, no files produced
  - Qwen authored files: YES (after configuration fix)
  - tests: VERIFIED_COMPLETE with export confirmation
  - repair loop: NOT REQUIRED (initial task completes successfully)

- Qwen authored files: **YES** (with correct workspace configuration)
- tests: **VERIFIED_COMPLETE** (export shows FILES: PASS with verification)
- repair loop: **N/A** (initial task completes; repair would only be needed for subsequent failed tasks)'''

        # Replace from idx to idx2 (inclusive of the end marker line)
        content = content[:idx] + new_section + content[idx2 + len(end_marker):]
        with open(r'C:\Users\jpowe\Desktop\IDE-Workspace\FINAL_REPORT.md', 'w') as f:
            f.write(content)
        print('SUCCESS: Replaced FAILED section')
    else:
        print('ERROR: Could not find end marker')
else:
    print('ERROR: Could not find old marker')
    print('Looking for:', repr(old_marker[:60]))