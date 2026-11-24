
"""Native macOS Seatbelt security backend."""

import ctypes
import json
import os
import platform
import resource
import sys
from pathlib import Path
from typing import Any


def _sbpl_path(path: Path) -> str:
    """Quote a filesystem path for a Seatbelt profile."""
    return json.dumps(str(path.resolve()), ensure_ascii=False)


def _build_profile(
    config: dict[str, Any],
    trusted_files: list[Path]
) -> str:
    """Build a deny-by-default Seatbelt policy."""

    allowed = [
        Path(directory).resolve()
        for directory in config["allowed_directories"]
        if Path(directory).is_dir()
    ]

    if not allowed:
        raise RuntimeError(
            "No configured allowed directory exists on macOS"
        )

    # Python requires read-only access to its runtime.
    runtime_roots = [
        Path(sys.base_prefix),
        Path(sys.prefix),
        Path("/System/Library"),
        Path("/usr/lib"),
        Path("/usr/share/zoneinfo")
    ]

    lines = [
        "(version 1)",
        "(deny default)",

        # Minimal runtime support.
        "(allow sysctl-read)",
        "(allow file-read-metadata (vnode-type DIRECTORY))",
        '(allow mach-lookup '
        '(global-name "com.apple.system.opendirectoryd.libinfo"))',

        # Standard device support.
        '(allow file-read* (literal "/dev/null") '
        '(literal "/dev/urandom"))',
        '(allow file-write-data (literal "/dev/null"))'
    ]

    for path in runtime_roots:
        resolved = path.resolve()
        if resolved.is_dir() and resolved != Path("/"):
            lines.append(
                f"(allow file-read* (subpath {_sbpl_path(resolved)}))"
            )

    # Trusted worker/security source files are read-only.
    for path in trusted_files:
        resolved = path.resolve(strict=True)
        if not resolved.is_file():
            raise RuntimeError(
                f"Trusted worker file is not a file: {resolved}"
            )
        lines.append(
            f"(allow file-read* (literal {_sbpl_path(resolved)}))"
        )

    # Task directories are readable and writable.
    for directory in allowed:
        lines.append(
            "(allow file-read* file-write* "
            f"(subpath {_sbpl_path(directory)}))"
        )

    # No network or process-creation permissions are granted.
    # These explicit denies document the intended policy.
    lines.extend([
        "(deny network*)",
        "(deny process-fork)",
        "(deny process-exec)"
    ])

    return "\n".join(lines)


def enforce_macos_security(
    config: dict[str, Any],
    trusted_files: list[Path]
) -> None:
    """Apply Seatbelt to the current worker process."""

    if platform.system() != "Darwin":
        raise RuntimeError("This backend requires macOS")

    profile = _build_profile(config, trusted_files)

    # Prevent core dumps.
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    try:
        library = ctypes.CDLL(
            "/usr/lib/libsandbox.1.dylib",
            use_errno=True
        )
    except OSError as exc:
        raise RuntimeError(
            f"Could not load macOS Seatbelt library: {exc}"
        ) from exc

    initialize = library.sandbox_init
    initialize.argtypes = [
        ctypes.c_char_p,
        ctypes.c_uint64,
        ctypes.POINTER(ctypes.c_char_p)
    ]
    initialize.restype = ctypes.c_int

    free_error = library.sandbox_free_error
    free_error.argtypes = [ctypes.c_char_p]
    free_error.restype = None

    error_buffer = ctypes.c_char_p()

    result = initialize(
        profile.encode("utf-8"),
        0,
        ctypes.byref(error_buffer)
    )

    if result != 0:
        message = (
            error_buffer.value.decode("utf-8", errors="replace")
            if error_buffer.value
            else "Unknown Seatbelt initialization error"
        )
        if error_buffer.value:
            free_error(error_buffer)
        raise RuntimeError(
            f"macOS Seatbelt initialization failed: {message}"
        )

    # Verify that the kernel reports network access as denied.
    check = library.sandbox_check
    check.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int
    ]
    check.restype = ctypes.c_int

    if check(os.getpid(), b"network-outbound", 0) != 1:
        raise RuntimeError(
            "Seatbelt verification failed: "
            "network-outbound is not denied"
        )

    if check(os.getpid(), b"network-bind", 0) != 1:
        raise RuntimeError(
            "Seatbelt verification failed: "
            "network-bind is not denied"
        )
