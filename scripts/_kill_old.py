import os, signal
for pid in [113889, 117030]:
    try:
        os.kill(pid, 0)
        print(f"{pid}: alive, killing...")
        os.kill(pid, 9)
        print(f"{pid}: killed")
    except ProcessLookupError:
        print(f"{pid}: not found (already dead)")
    except PermissionError:
        print(f"{pid}: no permission")
