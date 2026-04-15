"""Kill all python processes except uvicorn and this script."""
import os
import signal

my_pid = os.getpid()
parent_pid = os.getppid()

for entry in os.listdir("/proc"):
    if not entry.isdigit():
        continue
    pid = int(entry)
    if pid in (1, my_pid, parent_pid):
        continue
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            cmdline = f.read().decode("utf-8", errors="replace")
        if "analyze_all_library" in cmdline:
            print(f"Killing PID {pid}: {cmdline[:100]}")
            os.kill(pid, signal.SIGKILL)
        elif "demucs" in cmdline and "Rising to the Top" in cmdline:
            print(f"Killing PID {pid}: {cmdline[:100]}")
            os.kill(pid, signal.SIGKILL)
    except (PermissionError, FileNotFoundError, ProcessLookupError):
        pass
print("Done")
