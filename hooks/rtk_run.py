"""Run RTK with original diagnostics and an optional statistics access hint."""

import shutil
import subprocess
import sys


def main():
    executable = shutil.which("rtk")
    if executable is None:
        print("[rtk] RTK executable unavailable on PATH.", file=sys.stderr)
        return 127
    # Inherit stdout directly so compression output and binary streams survive.
    process = subprocess.Popen([executable, *sys.argv[1:]], stderr=subprocess.PIPE)
    for line in process.stderr:
        sys.stderr.buffer.write(line)
        sys.stderr.buffer.flush()
        if (sys.argv[1:2] == ["gain"]
                and b"Failed to initialize tracking database" in line
                and b"unable to open database file" in line):
            sys.stderr.buffer.write(
                b"[rtk] Statistics unavailable: check the RTK database path and directory permissions. "
                b"Persistent tracking requires read/write access to that directory. "
                b"Command compression can still work without saved statistics.\n"
            )
            sys.stderr.buffer.flush()
    process.stderr.close()
    return process.wait()


if __name__ == "__main__":
    sys.exit(main())
