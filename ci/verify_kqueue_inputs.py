import pathlib
import tomllib

board = tomllib.loads(pathlib.Path("board.toml").read_text())
args = board["payload"]["kernel_args"]
assert "native-ufs-probe=17" in args, args
assert "native-ufs-root=1" not in args, args

probe = pathlib.Path("package/BootUiTraceProbe.c").read_text()
assert "boot_kqueue_wait_describe" in probe
assert "KQ%c waits" in probe

resolver = pathlib.Path("package/BootKqueueWait.c").read_text()
assert "#include <sys/event_private.h>" in resolver
assert "kqf->kqf_count" in resolver

# The resolver is compiled by the UniXNU source-storage builder (libShengSourceStorage),
# which is the archive that links BootUiTraceProbe.o. Verify THAT builder, not legacy-display.
ss = pathlib.Path("../UniXNU/scripts/build-sheng-source-storage.py").read_text()
assert "BootKqueueWait.c" in ss, "resolver not registered in source-storage builder"

print("PASS: probe17 + v10 role trace + kqueue resolver are in the build (source-storage)")
