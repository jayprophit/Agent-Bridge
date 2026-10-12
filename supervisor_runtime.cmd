@echo off
REM Aetherius Supervisor Runtime launcher (§20 startup).
REM Persistent supervisor daemon — starts at logon WITHOUT any chat turn.
REM Uninstall: schtasks /Delete /TN AetheriusSupervisorRuntime /F
cd /d "C:\Users\jpowe\Desktop\Projects\Agent-Bridge-dashboard"
"C:\Users\jpowe\.aetherius\venvs\agent-bridge-verify\Scripts\python.exe" compute\supervisor_runtime.py --with-opencode --with-codex --state-dir supervisor_state --interval 120
