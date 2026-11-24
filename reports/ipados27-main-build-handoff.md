# Sheng iPadOS 27 main build handoff

Updated: 2026-11-24. This is a build handoff, not a device-boot qualification.
The previous startup repair report remains in `ipados27-startup-repair-2026-11-02.md`.
No `boot.img` from this CI line has been produced or tested on hardware.

## Scope and current pins

- Builder: `yeyingjun-codes/unixnu-sheng-fence`, workflow
  `.github/workflows/sheng-27-main-github.yml`, workflow id `427757211`, `main` branch.
  It runs on `macos-latest`, with a 360-minute job limit, and uses workflow dispatch.
- Device: `yeyingjun-codes/UniXNU-sheng`, branch `main-27-build`.
- UniXNU: `yeyingjun-codes/UniXNU`, branch `main-27`, currently pinned in the
  checkout step to `57f1126d880c8f315d61e1d11e4abbc1cda719d4`.
- UEFI: `UniXNU/uefi-sheng`, branch `sheng`.
- Required Actions secrets already configured: `GHTOKEN`, `UNIXNU_UNIQUE_CHIP_ID`,
  `SEED_PASSPHRASE`. Do not print their values.
- Current source-tree generation still creates `QcomGeniSpi` as a directory before
  assembly. The workflow removes that directory so the component can be linked.
  It also supplies the selected 27 OS profile and downloads the locked keyboard,
  WCN7850 and Ath12kWiFi inputs.

## Completed and observed in CI

### Earlier source and kernel-link work

- Created the UniXNU `main-27` branch from upstream `82b847c4ac3f68a57024b3082ffa3a03442defd9`.
  The old fork main lacked `patches/mesa/turnip-frame-diagnostics.patch`.
- `build-sheng-hid-input.py` now forwards non-iOS-17 builds to
  `build-sheng-source-drivers.py` and supplies `--tree` and `--device`.
- The mesa new-file header is repaired before applying patches.
- macOS-only `KeyboardProbe` and GOP compile warnings are handled for the iOS
  `-Werror` build without changing their logic.
- Weak-import probe stubs are injected after the real `.cache/xnu-work` clone,
  before XNU make, and registered in `osfmk/conf/files`. This includes
  `native_ram_block_volume_seed`. Earlier failures because `$WORK` was literal,
  the work tree did not yet exist, or the clone anchor did not match are resolved.
- These stubs are only for unresolved weak-import probe hooks. They are not a
  substitute for the real RamBlock, storage, display or boot implementations.

### GitHub Actions migration and reproducible inputs

- Replaced Codemagic for this build line. Fixed `CM_ENV` to `GITHUB_ENV`, toolchain
  path exports to `GITHUB_PATH`, expanded workspace paths, and output collection
  to `$GITHUB_WORKSPACE/out`.
- Installed and checked the macOS build toolchain, Rust and `ipsw`.
- Added pinned WCN7850 firmware downloads with size and SHA-256 verification.
- Materialized Ath12kWiFi's locked linux, freebsd and wpa_supplicant sources,
  including the required non-cone sparse checkout.
- Supplied the keyboard MCU firmware through the normal extraction step.
- The package step retries GitHub HTTP 403/429/5xx while restoring omitted
  DriverKit headers and receives `GITHUB_TOKEN` from `GHTOKEN`.
- Failure diagnostics retain runtime logs, LTO logs and `08-package.txt`.
- The current package retry count is one. The failure log collection condition
  was changed to match that single attempt.

### APFS Data seed is fixed

- `seed-data-grow.py` now prints failed command stdout/stderr.
- It retries APFS discovery for up to 30 seconds after raw-image attachment.
- Matching the raw attached device, `diskNs1`, or `DesignatedPhysicalStore` was
  not sufficient: on the runner the container's physical store could be a
  different disk number. The seed container is now found by its `Data` volume.
- Relevant fork commits: `b0c3b252f1a731c2393cbe509eeed653f4b71b01` (retry),
  `7fe8a38eda132719482d7ecf3bf0bfacdd3377e5` (partition match),
  `12e6228c7e00eb94fef74483643f4041775b2c86` (designated store),
  `99ad57837bb1ed4de13d23770c90c6fc85ec2069` (Data volume).
- Observed in later runs: Data UUID generation and seed creation succeed;
  runtime, GPU addon and Wi-Fi plugin building proceed past this stage.

### Component build attempts

- Added `component:VerifiedRoot`, `QcomGeniSpi`, `ShengNovatekTouch`,
  `VirtioMmioBlock`, `AirNir` and `Ath12kWifi` to the 27 kernel archives in
  `UniXNU-sheng/board.toml`.
- Added build recipes and changed `build_stage` from `embedded` to `kernel`
  for VerifiedRoot, QcomGeniSpi, ShengNovatekTouch, AirNir and Ath12kWifi in
  UniXNU `components.toml`. Current commit:
  `57f1126d880c8f315d61e1d11e4abbc1cda719d4`.
- The 95 kernel patches, IPSW acquisition, GPU/Wi-Fi runtime work and the
  fileset RELEASE reference build have all been observed to pass.
- **Caution:** the above component changes did not fix the final main-kernel
  link. They are retained as the current state, not claimed as a correct
  integration or proof that these components are linked.

## Current blocker

Latest executed run: **45301863101** (the 30th GitHub attempt). It failed in the
main XNU kernel link, after the previously failing seed and fileset stages.
The complete log is local at `artifacts/github-30/08-package.txt`.

The unresolved references are in these groups:

- RamBlock/storage: `_native_ram_block_gpu_addon`,
  `_native_source_storage_start`, `_native_verified_block_*`.
- Corecrypto/watchdog: `_corecrypto_kext_start`,
  `_sheng_boot_watchdog_policy`.
- Legacy display and boot progress: `_native_legacy_display_*`, `_boot_*`.

The main kernel link still does not include the required real archives/symbols.
Adding the components to `kernel.archives`, adding nonempty `build` recipes and
using `build_stage = "kernel"` did not remove these undefined references.

`build-xnu-4k-baseline.sh` conditionally force-loads archives based on
`XNU_NATIVE_RAM_BLOCK`, `XNU_NATIVE_LEGACY_DISPLAY`, `XNU_NATIVE_ADRENO` and
related environment switches. `sheng_ipados27_defconfig` contains the matching
`CONFIG_XNU_*` selections, but the defconfig-to-environment path and the exact
expected archive paths have not been proven end to end.

### Next investigation, not an approved rewrite

1. For one failing link, capture the effective `XNU_*` environment, the
  `KERNEL_EXTRA_ARCHIVES` value and the complete linker command.
2. For each missing group, locate the actually produced `.a`, inspect its symbols
  with `nm`, and compare that path with the script's conditional archive path.
  Example suspected path mismatch: `build/verified-root-xnu/libVerifiedRootProbe.a`
  versus a different component output directory. Verify rather than assume.
3. Trace `xnu_env(ctx)` and `archive_plan` in `scripts/unixnu/kernel.py`. The
  current `required` set only includes components with a nonempty `build` and
  `build_stage == "kernel"`; confirm whether the added recipes are valid for
  these components and whether they are selected for this tree.
4. Align the real build/link contract. Do **not** add these missing symbols to
  `native_weak_stubs.c`: their real implementations are required.
5. After a clean package succeeds, validate the manifest, image hashes,
  `ANDROID!` header and boot arguments, then separately arrange hardware
  `fastboot boot` testing. A successful build alone is not a boot success.

## Operational notes

- Codemagic's previous tokens failed with 401/402/403 and are not the active
  route. A replacement account could read `/apps` but could not create an app;
  do not spend time retrying that route for this task.
- Several GitHub runs (including 45192218539, 45195435528, 45230943668 and
  45273560633) were cancelled while queued and never built. Check for an active
  run before dispatching; do not count queue cancellation as a source failure.
- Keep the workflow's concurrency setting and avoid parallel dispatches.
- Latest diagnostics downloaded locally under `artifacts/github-30/`.
- Earlier `Codemagic` run 45072777163 passed its earlier link blocker but hit the
  two-hour build limit. The direct GitHub route is not subject to that limit.
- No new device test, successful final package or visual/Wi-Fi verification is
  claimed in this handoff.
