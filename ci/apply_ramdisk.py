#!/usr/bin/env python3
"""Teach UniXNURamDiskDxe to find the payload FAT inside a concatenated initrd.

On sheng the bootloader hands over one initrd that starts with the stock
vendor ramdisk (an LZ4 stream) and continues with the UniXNU payload, so the
published block device begins with compressed data and the FAT driver refuses
it. This scans the initrd for a FAT32 boot sector and publishes from there.
No behaviour change when the initrd already starts with the payload.
"""
import sys
from pathlib import Path

HELPER = '''STATIC
UINT64
FindFatBootSector (
  IN CONST UINT8  *Base,
  IN UINT64       Total
  )
{
  UINT64  Offset;

  if (Total < RAM_BLOCK_SIZE) {
    return 0;
  }

  for (Offset = 0; Offset + RAM_BLOCK_SIZE <= Total; Offset++) {
    CONST UINT8  *Sector;

    Sector = Base + Offset;
    if ((Sector[0] != 0xEB) || (Sector[510] != 0x55) || (Sector[511] != 0xAA)) {
      continue;
    }

    if (CompareMem (Sector + 82, "FAT32   ", 8) != 0) {
      continue;
    }

    if ((Sector[11] != 0x00) || (Sector[12] != 0x02)) {
      continue;
    }

    return Offset;
  }

  return 0;
}

'''

HELPER_ANCHOR = "STATIC\nVOID\nPublishInitrd (\n"

SHIFT_ANCHOR = "  mRamBase                = (UINT8 *)(UINTN)Start;\n"
SHIFT_PATCH = """  {
    UINT64  FatOffset;

    FatOffset = FindFatBootSector ((CONST UINT8 *)(UINTN)Start, End - Start);
    if (FatOffset != 0) {
      DEBUG ((DEBUG_ERROR, "UNIXNURAMDISK: payload FAT at +0x%lx\\n", FatOffset));
      Start += FatOffset;
    }
  }

  mRamBase                = (UINT8 *)(UINTN)Start;
"""


def main():
    path = Path(sys.argv[1])
    text = path.read_text()
    if "FindFatBootSector" in text:
        print("already patched:", path)
        return
    if text.count(HELPER_ANCHOR) != 1:
        raise SystemExit("helper anchor count %d != 1" % text.count(HELPER_ANCHOR))
    if text.count(SHIFT_ANCHOR) != 1:
        raise SystemExit("shift anchor count %d != 1" % text.count(SHIFT_ANCHOR))
    text = text.replace(HELPER_ANCHOR, HELPER + HELPER_ANCHOR, 1)
    text = text.replace(SHIFT_ANCHOR, SHIFT_PATCH, 1)
    path.write_text(text)
    print("patched ramdisk driver:", path)


if __name__ == "__main__":
    main()
