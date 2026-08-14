import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "tools" / "configure_nas_automount.py"
SPEC = importlib.util.spec_from_file_location("configure_nas_automount", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_adds_automount_without_exposing_or_replacing_credentials() -> None:
    source = (
        "//nas/share /mnt/nas/harbeat cifs "
        "credentials=/root/secret,uid=1000,_netdev,nofail 0 0\n"
    )
    updated, options = MODULE.update_fstab(source, "/mnt/nas/harbeat")

    assert "credentials=/root/secret" in updated
    assert "x-systemd.automount" in options
    assert "x-systemd.mount-timeout=60" in options
    assert updated.count("_netdev") == 1
