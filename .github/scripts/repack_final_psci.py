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
fd = raw[176:]
assert raw[56:60] == b'ARM\x64' and len(fd) == 0x300000
assert hashlib.sha256(fd).hexdigest() == EXPECTED_FD
shim = bytearray(raw[:176])
# Original copy/cache path in no-fb shim occupies 0x48..0x90 only when no timer;
# rebuild canonical upstream shim with a single PSCI SMC at the normal final branch.
source = WORK / 'uefi-sheng/BootShim/BootShim.S'
text = source.read_text()
text = text.replace('_Entry:\n', '''_Entry:
  ldr w0, =0x84000009
  mov x1, xzr
  mov x2, xzr
  mov x3, xzr
  smc #0
_ResetDead:
  wfe
  b _ResetDead
_UnusedEntry:
''', 1)
(WORK / 'BootShimFinalReset.S').write_text(text)
subprocess.run(['clang', '--target=aarch64-linux-gnu', '-c', WORK / 'BootShimFinalReset.S',
                '-o', WORK / 'BootShimFinalReset.o', '-DREQUIRES_KERNEL_HEADER=1',
                '-DFD_BASE=0xa7100000', '-DFD_SIZE=0x300000'], check=True)
elf = (WORK / 'BootShimFinalReset.o').read_bytes()
assert elf[:4] == b'\x7fELF' and elf[4] == 2 and elf[5] == 1
phoff = struct.unpack_from('<Q', elf, 32)[0]
phentsize, phnum = struct.unpack_from('<HH', elf, 54)
shoff = struct.unpack_from('<Q', elf, 40)[0]
shentsize, shnum, shstrndx = struct.unpack_from('<HHH', elf, 58)
sections = []
for index in range(shnum):
    offset = shoff + index * shentsize
    fields = struct.unpack_from('<IIQQQQIIQQ', elf, offset)
    sections.append(fields)
strhdr = sections[shstrndx]
strings = elf[strhdr[4]:strhdr[4] + strhdr[5]]
def section_name(fields):
    end = strings.index(0, fields[0])
    return strings[fields[0]:end].decode()
loads = []
for index in range(phnum):
    offset = phoff + index * phentsize
    p_type, p_flags, p_offset, p_vaddr, p_paddr, p_filesz, p_memsz, p_align = struct.unpack_from('<IIQQQQQQ', elf, offset)
    if p_type == 1 and p_filesz:
        loads.append((p_paddr, elf[p_offset:p_offset + p_filesz]))
if not loads:
    for fields in sections:
        if fields[1] == 1 and fields[2] & 2 and fields[5]:
            loads.append((fields[3], elf[fields[4]:fields[4] + fields[5]]))
assert loads, [(section_name(s), s[3], s[5]) for s in sections]
print('ELF sections', [(section_name(s), hex(s[3]), s[5]) for s in sections], flush=True)
base = min(address for address, _ in loads)
end = max(address + len(data) for address, data in loads)
binary = bytearray(end - base)
for address, data in loads:
    binary[address - base:address - base + len(data)] = data
(WORK / 'BootShimFinalReset.bin').write_bytes(binary)
shim = (WORK / 'BootShimFinalReset.bin').read_bytes()
print('header compare', shim[:4].hex(), raw[:4].hex(), shim[8:16].hex(), raw[8:16].hex(), shim[56:60].hex(), flush=True)
assert shim[:4] == raw[:4] and shim[8:16] == raw[8:16] and shim[56:60] == b'ARM\x64'
assert bytes.fromhex('030000d4') in shim[:len(shim)]
new_kernel = gzip.compress(shim + fd, mtime=0) + dtb
(WORK / 'final.Image.gz-dtb').write_bytes(new_kernel)
(WORK / 'ramdisk').write_bytes(b'')
mkbootimg = WORK / 'uefi-sheng/Resources/Scripts/mkbootimg.py'
subprocess.run(['python3', mkbootimg, '--kernel', WORK / 'final.Image.gz-dtb',
                '--ramdisk', WORK / 'ramdisk', '-o', WORK / 'probe-final-psci.img',
                '--base', '0', '--kernel_offset', '32768', '--tags_offset', '31457280',
                '--pagesize', '4096', '--header_version', '0'], check=True)
image = (WORK / 'probe-final-psci.img').read_bytes()
assert image[:8] == b'ANDROID!' and struct.unpack_from('<I', image, 36)[0] == 4096
assert struct.unpack_from('<I', image, 40)[0] == 0 and struct.unpack_from('<I', image, 16)[0] == 0
size = struct.unpack_from('<I', image, 8)[0]
assert image[4096:4096 + size] == new_kernel
OUT.mkdir(parents=True, exist_ok=True)
(OUT / 'probe-final-psci.img').write_bytes(image)
(OUT / 'BootShimFinalReset.S').write_text(text)
report = {'variant': 'upstream-copy-cache-final-psci', 'source_sha256': EXPECTED_OLD,
          'fd_sha256': EXPECTED_FD, 'dtb_sha256': hashlib.sha256(dtb).hexdigest(),
          'image_bytes': len(image), 'image_sha256': hashlib.sha256(image).hexdigest(),
          'shim_bytes': len(shim), 'timer_removed': True, 'framebuffer_marker': False,
          'qemu_tested': False, 'hardware_tested': False}
(OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2), flush=True)
