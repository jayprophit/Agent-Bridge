# Device I/O Capabilities (v0.7)

Presence detection only — discovery never activates or records from devices.

## States

- `HARDWARE_PRESENT`: device enumerated by the OS.
- `NOT_PRESENT`: enumeration succeeded, nothing found.
- `PERMISSION_UNKNOWN`: enumeration failed or permission state unknowable
  (hardware presence does not imply permission).
- `AVAILABLE` / `DENIED`: reserved for future permission-aware checks.

## Windows method

- Camera: `Get-PnpDevice -Class Camera,Image` with `Status OK`
  (return code ignored; content decides, since PnP may exit nonzero).
- Microphone/speaker: MMDevices `Audio\Capture` / `Audio\Render` key presence.
- This machine: Logi C270 webcam, microphone and speaker endpoints present.

## Package managers

`pip, npm, node, winget, choco, git` via `PATH` lookup. Detection only —
never install, update, or remove packages.

This machine: pip, npm, node, winget, choco, git all detected.
