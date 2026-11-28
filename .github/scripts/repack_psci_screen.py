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
dec = zlib.decompressobj(16 + zlib.MAX_WBITS)
raw = dec.decompress(old[page:page + kernel_size])
dtb = dec.unused_data
fd = raw[176:]
assert raw[56:60] == b'ARM\x64' and len(fd) == 0x300000
assert hashlib.sha256(fd).hexdigest() == EXPECTED_FD

source = ROOT / '.github/scripts/BootShimPsciScreen.S'
text = source.read_text()
(WORK / 'BootShimPsciScreen.S').write_text(text)
subprocess.run(['clang', '--target=aarch64-linux-gnu', '-c', WORK / 'BootShimPsciScreen.S',
                '-o', WORK / 'BootShimPsciScreen.o', '-DREQUIRES_KERNEL_HEADER=1',
                '-DFD_BASE=0xa7100000', '-DFD_SIZE=0x300000'], check=True)
subprocess.run(['llvm-objcopy', '-O', 'binary', '--only-section=.text',
                WORK / 'BootShimPsciScreen.o', WORK / 'BootShimPsciScreen.bin'], check=True)
shim = (WORK / 'BootShimPsciScreen.bin').read_bytes()
first = struct.unpack_from('<I', shim)[0]
assert (first & 0x9f000000) == 0x10000000 and (first & 31) == 1, hex(first)
assert shim[4:8] == bytes.fromhex('0f000014')
assert shim[8:16] == raw[8:16] and shim[56:60] == b'ARM\x64'
assert shim.count(bytes.fromhex('030000d4')) == 2
assert bytes.fromhex('04e03bd5') not in shim
assert bytes.fromhex('25e03bd5') not in shim
assert shim[16:20] == struct.pack('<I', len(shim) + len(fd))
new_kernel = gzip.compress(shim + fd, mtime=0) + dtb
(WORK / 'screen.Image.gz-dtb').write_bytes(new_kernel)
(WORK / 'ramdisk').write_bytes(b'')
mkbootimg = WORK / 'uefi-sheng/Resources/Scripts/mkbootimg.py'
subprocess.run(['python3', mkbootimg, '--kernel', WORK / 'screen.Image.gz-dtb',
                '--ramdisk', WORK / 'ramdisk', '-o', WORK / 'probe-psci-screen.img',
                '--base', '0', '--kernel_offset', '32768', '--tags_offset', '31457280',
                '--pagesize', '4096', '--header_version', '0'], check=True)
image = (WORK / 'probe-psci-screen.img').read_bytes()
assert image[:8] == b'ANDROID!' and struct.unpack_from('<I', image, 36)[0] == 4096
assert struct.unpack_from('<I', image, 40)[0] == 0 and struct.unpack_from('<I', image, 16)[0] == 0
size = struct.unpack_from('<I', image, 8)[0]
assert image[4096:4096 + size] == new_kernel
check = zlib.decompressobj(31)
check_raw = check.decompress(new_kernel)
assert check_raw[:len(shim)] == shim
assert hashlib.sha256(check_raw[len(shim):]).hexdigest() == EXPECTED_FD
OUT.mkdir(parents=True, exist_ok=True)
(OUT / 'probe-psci-screen.img').write_bytes(image)
(OUT / 'BootShimPsciScreen.S').write_text(text)
(OUT / 'BootShimPsciScreen.bin').write_bytes(shim)
subprocess.run(['llvm-objdump', '-D', '--triple=aarch64', WORK / 'BootShimPsciScreen.o'],
               stdout=(OUT / 'disassembly.txt').open('w'), check=True)
report = {'variant': 'psci-version-features-screen', 'source_sha256': EXPECTED_OLD,
          'fd_sha256': EXPECTED_FD, 'dtb_sha256': hashlib.sha256(dtb).hexdigest(),
          'image_bytes': len(image), 'image_sha256': hashlib.sha256(image).hexdigest(),
          'shim_bytes': len(shim), 'timer_removed': True, 'framebuffer_marker': True,
          'display': 'white entry square + VERSION row + FEATURES(SYSTEM_RESET) row, 8 nibbles each',
          'encoding': 'each nibble = 4 vertical bars, MSB to LSB, each set bit lights a 10x60 column',
          'expected': 'VERSION should be 00010002 for PSCI 1.2; FEATURES supported should be 00000000; NOT_SUPPORTED is ffffffff',
          'qemu_tested': False, 'hardware_tested': False}
(OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2), flush=True)
