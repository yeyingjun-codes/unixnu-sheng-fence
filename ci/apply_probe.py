#!/usr/bin/env python3
"""Add read-only probes to UniXNU Config.c and surface the results in the menu title.

Collects, at config load time (right after UniXNUConnectAll()):
  b  = BlockIo handle count
  d  = DiskIo handle count
  f  = SimpleFileSystem handle count
  r  = status of the first per-volume unixnu.toml read attempt
  bs = BlockSize of the first BlockIo device
  lb = LastBlock of the first BlockIo device
  l0 = first four bytes of that device's LBA 0
  sg = bytes 510..511 of that device's LBA 0 (0xaa55 means a boot signature)

The values are printed into the menu title, because UniXNULog is filtered out
by the platform's debug mask and never reaches the screen.

No behaviour changes: counters, one read of LBA 0, and a title string.
"""
import sys
from pathlib import Path

INC_ANCHOR = '#include "Internal.h"\n'
INCLUDES = "".join([
    "\n",
    "#include <Protocol/BlockIo.h>\n",
    "#include <Protocol/DiskIo.h>\n",
    "\n",
    "STATIC UINTN    mProbeBlock;\n",
    "STATIC UINTN    mProbeDisk;\n",
    "STATIC UINTN    mProbeFs;\n",
    "STATIC UINTN    mProbeReadStatus;\n",
    "STATIC BOOLEAN  mProbeReadSeen;\n",
    "STATIC UINTN    mProbeBlockSize;\n",
    "STATIC UINTN    mProbeLastBlock;\n",
    "STATIC UINT32   mProbeL0;\n",
    "STATIC UINT32   mProbeSig;\n",
])

ZERO_ANCHOR = "  ZeroMem (Config, sizeof (*Config));\n  Loaded = FALSE;\n"

PROBE = "".join([
    "  ZeroMem (Config, sizeof (*Config));\n",
    "  Loaded = FALSE;\n",
    "\n",
    "  {\n",
    "    EFI_HANDLE  *BioHandles;\n",
    "    UINTN       BioCount;\n",
    "    EFI_HANDLE  *Probe;\n",
    "    UINTN       DiskCount;\n",
    "    UINTN       FsCount;\n",
    "\n",
    "    BioHandles = NULL;\n",
    "    BioCount   = 0;\n",
    "    if (EFI_ERROR (gBS->LocateHandleBuffer (ByProtocol, &gEfiBlockIoProtocolGuid, NULL, &BioCount, &BioHandles))) {\n",
    "      BioCount = 0;\n",
    "    }\n",
    "\n",
    "    Probe = NULL;\n",
    "    if (EFI_ERROR (gBS->LocateHandleBuffer (ByProtocol, &gEfiDiskIoProtocolGuid, NULL, &DiskCount, &Probe))) {\n",
    "      DiskCount = 0;\n",
    "    } else {\n",
    "      FreePool (Probe);\n",
    "    }\n",
    "\n",
    "    Probe = NULL;\n",
    "    if (EFI_ERROR (gBS->LocateHandleBuffer (ByProtocol, &gEfiSimpleFileSystemProtocolGuid, NULL, &FsCount, &Probe))) {\n",
    "      FsCount = 0;\n",
    "    } else {\n",
    "      FreePool (Probe);\n",
    "    }\n",
    "\n",
    "    mProbeBlock = BioCount;\n",
    "    mProbeDisk  = DiskCount;\n",
    "    mProbeFs    = FsCount;\n",
    "\n",
    "    if (BioCount > 0) {\n",
    "      EFI_BLOCK_IO_PROTOCOL  *Bio;\n",
    "      UINT8                  *Sector;\n",
    "\n",
    "      Bio    = NULL;\n",
    "      Sector = AllocateZeroPool (512);\n",
    "      if ((Sector != NULL) &&\n",
    "          !EFI_ERROR (gBS->HandleProtocol (BioHandles[0], &gEfiBlockIoProtocolGuid, (VOID **)&Bio)) &&\n",
    "          (Bio != NULL))\n",
    "      {\n",
    "        mProbeBlockSize = (UINTN)Bio->Media->BlockSize;\n",
    "        mProbeLastBlock = (UINTN)Bio->Media->LastBlock;\n",
    "        if (!EFI_ERROR (Bio->ReadBlocks (Bio, Bio->Media->MediaId, 0, 512, Sector))) {\n",
    "          mProbeL0  = ((UINT32)Sector[0] << 24) | ((UINT32)Sector[1] << 16) | ((UINT32)Sector[2] << 8) | (UINT32)Sector[3];\n",
    "          mProbeSig = ((UINT32)Sector[510] << 8) | (UINT32)Sector[511];\n",
    "        }\n",
    "      }\n",
    "\n",
    "      if (Sector != NULL) {\n",
    "        FreePool (Sector);\n",
    "      }\n",
    "    }\n",
    "\n",
    "    if (BioHandles != NULL) {\n",
    "      FreePool (BioHandles);\n",
    "    }\n",
    "\n",
    '    UniXNULog ("probe: blockio %u diskio %u simplefs %u", (UINT32)BioCount, (UINT32)DiskCount, (UINT32)FsCount);\n',
    "  }\n",
])

READ_ANCHOR = "".join([
    "  Status = UniXNUReadFile (Volume, (CONST CHAR16 *)PcdGetPtr (PcdUniXNUConfigPath), (VOID **)&Text, &Size);\n",
    "  if (EFI_ERROR (Status)) {\n",
    "    return FALSE;\n",
    "  }\n",
])

READ_PATCH = "".join([
    "  Status = UniXNUReadFile (Volume, (CONST CHAR16 *)PcdGetPtr (PcdUniXNUConfigPath), (VOID **)&Text, &Size);\n",
    "  if (EFI_ERROR (Status)) {\n",
    "    if (!mProbeReadSeen) {\n",
    "      mProbeReadSeen   = TRUE;\n",
    "      mProbeReadStatus = (UINTN)Status;\n",
    "    }\n",
    "\n",
    '    UniXNULog ("probe: volume 0x%lx read %r", (UINT64)(UINTN)Volume, Status);\n',
    "    return FALSE;\n",
    "  }\n",
])

TITLE_ANCHOR = "  Config->SourceLabel = AllocateCopyPool (StrSize (Label), Label);\n"

TITLE_PATCH = "".join([
    "  Config->SourceLabel = AllocateCopyPool (StrSize (Label), Label);\n",
    "\n",
    "  {\n",
    "    CHAR16  *ProbeTitle;\n",
    "    UINTN   ProbeChars;\n",
    "\n",
    "    ProbeChars = 192;\n",
    "    ProbeTitle = AllocateZeroPool (ProbeChars * sizeof (CHAR16));\n",
    "    if (ProbeTitle != NULL) {\n",
    "      UnicodeSPrint (\n",
    "        ProbeTitle,\n",
    "        ProbeChars * sizeof (CHAR16),\n",
    '        L"%s [b%u d%u f%u r%x bs%u lb%u l0%08x sg%04x]",\n',
    '        (Config->Title != NULL) ? Config->Title : L"UniXNU",\n',
    "        (UINT32)mProbeBlock,\n",
    "        (UINT32)mProbeDisk,\n",
    "        (UINT32)mProbeFs,\n",
    "        (UINT64)mProbeReadStatus,\n",
    "        (UINT32)mProbeBlockSize,\n",
    "        (UINT32)mProbeLastBlock,\n",
    "        (UINT32)mProbeL0,\n",
    "        (UINT32)mProbeSig\n",
    "        );\n",
    "      Config->Title = ProbeTitle;\n",
    "    }\n",
    "  }\n",
])

INF_ANCHOR = "  gEfiPartitionInfoProtocolGuid     ## SOMETIMES_CONSUMES\n"
INF_LINE = "  gEfiDiskIoProtocolGuid            ## SOMETIMES_CONSUMES\n"


def patch_inf(cfg):
    inf = cfg.with_name("UniXNULib.inf")
    if not inf.is_file():
        return
    text = inf.read_text()
    if "gEfiDiskIoProtocolGuid" in text:
        return
    if text.count(INF_ANCHOR) != 1:
        raise SystemExit("inf anchor count %d != 1" % text.count(INF_ANCHOR))
    inf.write_text(text.replace(INF_ANCHOR, INF_LINE + INF_ANCHOR, 1))
    print("patched inf:", inf)


def main():
    path = Path(sys.argv[1])
    text = path.read_text()
    if "probe: blockio" in text:
        print("already patched:", path)
        return
    for anchor, name in ((INC_ANCHOR, "include"),
                         (ZERO_ANCHOR, "ZeroMem"),
                         (READ_ANCHOR, "read"),
                         (TITLE_ANCHOR, "title")):
        if text.count(anchor) != 1:
            raise SystemExit("%s anchor count %d != 1" % (name, text.count(anchor)))
    text = text.replace(INC_ANCHOR, INC_ANCHOR + INCLUDES, 1)
    text = text.replace(ZERO_ANCHOR, PROBE, 1)
    text = text.replace(READ_ANCHOR, READ_PATCH, 1)
    text = text.replace(TITLE_ANCHOR, TITLE_PATCH, 1)
    path.write_text(text)
    print("patched:", path)
    patch_inf(path)


if __name__ == "__main__":
    main()
