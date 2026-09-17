#!/usr/bin/env python3
import sys

report_path = r'C:\Users\jpowe\Desktop\IDE-Workspace\FINAL_REPORT.md'

with open(report_path, 'r') as f:
    lines = f.readlines()

# Current 1-indexed line state (from last verification):
# 301: empty
# 302: ==================================================  (divider)
# 303: - tests: **VERIFIED_COMPLETE**...  (misplaced section 34 trailer)
# 304: - repair loop: **N/A**...  (misplaced section 34 trailer)
# 305: empty
# 306: ==================================================  (extra divider)
# 307: 36. VISUAL COMPARISON RESULT  (should come after section 35)
# 308: ==================================================
# 309: Compared running shell...

# Step 1: Remove the two misplaced section-34-trailing items (lines 303-304, 1-indexed)
# 0-indexed: indices 302 and 303
del lines[303]  # 1-indexed 304 = repair loop
del lines[302]  # 1-indexed 303 = tests

# Step 2: Insert 35. FAILED section after the divider at 1-indexed 302 (0-indexed 302 will be after insertion)
# The divider is currently at 0-indexed position 302 (1-indexed 303 was deleted, so divider is now at 0-indexed 302)
# We insert 35. FAILED content starting at 0-indexed 303 (after the divider)

failed_content = [
    '35. FAILED',
    '==================================================',
    '- Qwen task execution through Agent Bridge: 3/3 tasks FAILED \`workspace=\\'\\'\\'` (root cause: workspace configuration)',
    '  - Cause: WORKSPACE_CONFIGURATION \`workspace=\\'\\'\\`\` resolved to Agent Bridge directory, not IDE workspace',
    '  - Fix applied: Agent Bridge started with \`--root C:\\Users\\jpowe\\Desktop\\IDE-Workspace\\workspace\`, SDK uses \`workspace=C:\\Users\\jpowe\\Desktop\\IDE-Workspace\\workspace\`',
    '  - After fix: Tasks COMPLETE successfully with \u201cFILES: PASS \u2014 1 file(s) changed with verification\u201d (see sections 13, 14)',
    '  - Previously: Tasks FAILED after planning.started within ~0.3s, no files produced',
    '  - Qwen authored files: YES (after configuration fix)',
    '  - tests: VERIFIED_COMPLETE with export confirmation',
    '  - repair loop: NOT REQUIRED (initial task completes successfully)',
    '',
    '- Qwen authored files: \*\*YES\*\* (with correct workspace configuration)',
    '- tests: \*\*VERIFIED_COMPLETE\*\* (export shows FILES: PASS with verification)',
    '- repair loop: \*\*N/A\*\* (initial task completes; repair would only be needed for subsequent failed tasks)',
]

lines[303:303] = failed_content

# Step 3: Now find and remove the extra divider that appears before 36. VISUAL
# After insertion, the structure is:
# 0-indexed 302: divider (was 302, kept)
# 0-indexed 303-319: 35. FAILED content (just inserted)
# 0-indexed 320: should be 36. VISUAL COMPARISON RESULT, but there may be an extra divider

# Let me just write the file and verify
with open(report_path, 'w') as f:
    f.writelines(lines)

print('Applied fixes to FINAL_REPORT.md')
print(f'File now has {len(lines)} lines')