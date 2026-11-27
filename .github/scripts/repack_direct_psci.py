import gzip
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import zlib

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / 'work'
OUT = ROOT / 'out/diag/probe'
OLD = WORK / 'probe-reset-no-fb.img'
EXPECTED_OLD = 'eb2297728d3a3b3fc1287a818685f4f5c4f8024f0aafc891ffecfd91007168f4'
EXPECTED_FD = '5a7dc00b4145c16de8df59f15793edc09e712f2fa03c6109bddb5f54c7a16a32'

old = OLD.read_bytes()
assert hashlib.sha256(old).hexdigest() == EXPECTED_OLD
kernel_size = struct.unpack_from('<I', old, 8)[0]
page = struct.unpack_from('<I', old, 36)[0]
kernel = old[page:page + kernel_size]
dec = zlib.decompressobj(16 + zlib.MAX_WBITS)
raw = dec.decompress(kernel)
dtb = dec.unused_data
shim = bytearray(raw[:176])
fd = raw[176:]
assert shim[56:60] == b'ARM\x64' and len(fd) == 0x300000
assert hashlib.sha256(fd).hexdigest() == EXPECTED_FD
assert shim[0x48:0x4c] == bytes.fromhex('04e03bd5')
body = [0x180002c0, 0xaa1f03e1, 0xaa1f03e2, 0xaa1f03e3, 0xd4000003,
        0xd503205f, 0x17ffffff]
body.extend([0xd503201f] * ((0x8c - 0x48) // 4 - len(body)))
shim[0x48:0x8c] = b''.join(struct.pack('<I', instruction) for instruction in body)
assert bytes.fromhex('04e03bd5') not in shim[:0x8c]
assert bytes.fromhex('25e03bd5') not in shim[:0x8c]
assert shim[0x58:0x5c] == bytes.fromhex('030000d4')
new_kernel = gzip.compress(bytes(shim) + fd, mtime=0) + dtb
(WORK / 'direct.Image.gz-dtb').write_bytes(new_kernel)
(WORK / 'ramdisk').write_bytes(b'')
mkbootimg = WORK / 'uefi-sheng/Resources/Scripts/mkbootimg.py'
subprocess.run(['python3', mkbootimg, '--kernel', WORK / 'direct.Image.gz-dtb',
                '--ramdisk', WORK / 'ramdisk', '-o', WORK / 'probe-direct-psci.img',
                '--base', '0', '--kernel_offset', '32768', '--tags_offset', '31457280',
                '--pagesize', '4096', '--header_version', '0'], check=True)
image = (WORK / 'probe-direct-psci.img').read_bytes()
assert image[:8] == b'ANDROID!'
assert struct.unpack_from('<I', image, 36)[0] == 4096
assert struct.unpack_from('<I', image, 40)[0] == 0
assert struct.unpack_from('<I', image, 16)[0] == 0
size = struct.unpack_from('<I', image, 8)[0]
assert image[4096:4096 + size] == new_kernel
OUT.mkdir(parents=True, exist_ok=True)
(OUT / 'probe-direct-psci.img').write_bytes(image)
report = {'variant': 'direct-psci-no-fb-no-timer', 'source_sha256': EXPECTED_OLD,
          'fd_sha256': EXPECTED_FD, 'dtb_sha256': hashlib.sha256(dtb).hexdigest(),
          'image_bytes': len(image), 'image_sha256': hashlib.sha256(image).hexdigest(),
          'shim_bytes': len(shim), 'timer_removed': True, 'framebuffer_marker': False,
          'qemu_tested': False, 'hardware_tested': False}
(OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2), flush=True)
