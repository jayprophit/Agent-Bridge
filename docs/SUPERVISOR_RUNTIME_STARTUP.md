# Supervisor Runtime — startup registration (OWNER GATE, §20/§27)

`schtasks /Create` requires an elevated shell (Access denied in the standard
session). This is an unavoidable OS permission gate — the ONE class of gate
that requires the owner. Everything else about the runtime is autonomous.

## Owner action (one command, elevated PowerShell):

```powershell
schtasks /Create /TN "AetheriusSupervisorRuntime" /TR "C:\Users\jpowe\Desktop\Projects\Agent-Bridge-dashboard\supervisor_runtime.cmd" /SC ONLOGON /RL LIMITED /F
```

## Start it NOW (no elevation needed — works in any shell):

```bash
"C:/Users/jpowe/Desktop/Projects/Agent-Bridge-dashboard/supervisor_runtime.cmd"
```

## Status / uninstall:

```bash
python compute/supervisor_runtime.py --status --state-dir supervisor_state
schtasks /Query /TN AetheriusSupervisorRuntime /FO LIST     # if registered
schtasks /Delete /TN AetheriusSupervisorRuntime /F          # reversible
```

## What the gate does NOT block

The runtime itself is fully built, tested (16/16), live-verified against the
real workers, and currently RUNNING as a daemon (started without elevation).
The gate only covers *automatic start at logon* — the programme continues
regardless (§27: block only that task, continue everything else).
