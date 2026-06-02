"""UTF-8 für die Windows-Konsole erzwingen.

Hintergrund:
LinkedIn-Posts enthalten oft Mathematical-Bold-Zeichen (U+1D400ff., z.B.
"Was" in Bold-Math), die als 4-Byte-UTF-8 kodiert werden. Windows-cmd und
manche PowerShell-Versionen default'n auf cp1252 oder die System-OEM-Codepage
und rendern diese Sequenzen als Mojibake.

Lösung in zwei Schichten:
1. Win32 SetConsoleCP / SetConsoleOutputCP auf 65001 (= UTF-8) setzen.
2. sys.stdout / stderr / stdin auf UTF-8 reconfigure'n, damit Python
   intern auch UTF-8 schreibt.

Beides ist nötig — nur eines reicht nicht.
"""

from __future__ import annotations

import contextlib
import sys


def enable_utf8_console() -> None:
    """No-op auf Nicht-Windows. Auf Windows: Codepage + Streams auf UTF-8."""
    if sys.platform != "win32":
        return

    # 1) Windows Console Codepage auf UTF-8 (65001)
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        kernel32.SetConsoleCP(65001)
        kernel32.SetConsoleOutputCP(65001)
    except Exception:
        # Kein hartes Failure — wir versuchen weiter, Streams zu reconfigure'n
        pass

    # 2) Python-Streams auf UTF-8 reconfigure'n
    for stream_name in ("stdout", "stderr", "stdin"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            with contextlib.suppress(Exception):
                stream.reconfigure(encoding="utf-8", errors="replace")
