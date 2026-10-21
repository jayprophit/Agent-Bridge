"""Canonicalise a workspace path on Windows, and compare two of them.

Windows keeps a short form of a path, with a tilde in it, beside the
long form, and the two name the same directory. Path.resolve() does not
expand the short form, so a temporary directory handed to the runtime
in the short spelling and recorded in the long one is treated as two
places. The consequence was a workspace that was refused as being
outside the root it was in, and a session label that was refused for
belonging to a workspace it belonged to.

So the short name is expanded, and the comparison is by identity rather
than by spelling.
"""

from __future__ import annotations

import os
from pathlib import Path


def _long_path(path: str) -> str:
    """The long form of a Windows path, when there is one.

    GetLongPathNameW turns C:\\Users\\RUNNER~1\\... into
    C:\\Users\\runneradmin\\... It is not available everywhere, and
    nothing is lost when it is not: the path is then simply used as it
    is.
    """
    if os.name != "nt":
        return path
    try:
        import ctypes
        from ctypes import wintypes

        get_long = ctypes.windll.kernel32.GetLongPathNameW
        get_long.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR,
                            wintypes.DWORD]
        get_long.restype = wintypes.DWORD
        size = get_long(path, None, 0)
        if not size:
            return path
        buffer = ctypes.create_unicode_buffer(size)
        if get_long(path, buffer, size):
            return buffer.value
    except Exception:
        return path
    return path


def canonical_workspace(path: str | Path) -> Path:
    """The canonical form of a workspace path.

    Absolute, with the short name expanded, so that two spellings of
    one directory give one answer.
    """
    raw = str(path).strip()
    if not raw:
        return Path(raw)
    absolute = os.path.abspath(os.path.expanduser(raw))
    try:
        resolved = str(Path(absolute).resolve())
    except OSError:
        resolved = absolute
    return Path(_long_path(resolved))


def same_workspace(one: str | Path, other: str | Path) -> bool:
    """Whether two paths name the same directory.

    The comparison is by identity where the platform can tell, and by
    the canonical form otherwise.
    """
    a = canonical_workspace(one)
    b = canonical_workspace(other)
    if a == b:
        return True
    try:
        return os.path.samefile(str(a), str(b))
    except OSError:
        return False
