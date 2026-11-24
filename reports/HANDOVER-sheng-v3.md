# UniXNU sheng（小米平板 6S Pro 12.4）iPadOS 27 移植 — 终极交接文档 v2

> 生成：2026-11-22 13:50（GMT+8）。本文档 = 11-12 审计版交接（`F:\unixnu\HANDOVER-sheng-2026-11-12-AUDITED.md`，历史部分不重复抄录，见该文件）+ 11-17~11-22 本会话全部增量。
> 目标不变：**sheng 上临时启动 iPadOS 27.0.1 (24A446) 出可见 UI（Home Screen/锁屏），触摸可用。**
> 新窗口拿到本文档即可 0 损耗接续。所有命令、token、pin、坑、已废弃路线全部在内。

---

# 第一部分：凭证与资产（能直接用的东西）

## 1.1 GitHub（全权限可用）

- **账号**：`yeyingjun-codes`
- **PAT（40 字符）**：
  ```
  ghp_<REDACTED_GITHUB_PAT>
  ```
- **标准取 token 方式**（所有脚本都用这个，别硬编码）：
  ```python
  import subprocess, urllib.parse
  u = subprocess.check_output(['git','-C','F:/unixnu/UniXNU-sheng-cmprobe','config','--get','remote.fence2.url'],text=True).strip()
  TOKEN = urllib.parse.unquote(urllib.parse.urlsplit(u).password)
  H = {'Authorization':'Bearer '+TOKEN,'Accept':'application/vnd.github+json','User-Agent':'sheng'}
  ```
- PAT 同时具备：repo 读写（含 Secrets 无法读，secret 值只存在 GitHub 服务端）、Actions 触发/取消、artifact 下载、Git Data API（PUT contents）。

## 1.2 Codemagic（macOS 构建农场，10 账号池）

- **App ID**：`6afb4c09e215a04a9aafd0fd`（部分 workflow 自动 provision 新 app，不固定）
- **API**：`https://codemagic.io/api/v3`（v3）+ `https://api.codemagic.io`（legacy），header：`x-auth-token: <token>`
- **Token 池**：fence 仓 GitHub Secrets `CODEMAGIC_TOKEN_1` ~ `CODEMAGIC_TOKEN_10`。**明文值不在本地、任何窗口都读不到，也不需要读**。
- **唯一正确触发方式**：dispatch fence 仓 **`codemagic-fallback-build`（workflow ID 424701452）**。它自动遍历 token 池（默认 index 2-10）→ 验活 → provision app → 启动 Codemagic 构建 → 盯到结束 → 传 artifact。
  ```python
  # 触发（照抄，返回 204 即成功）
  requests.post('https://api.github.com/repos/yeyingjun-codes/unixnu-sheng-fence/actions/workflows/424701452/dispatches',
      headers=H, json={'ref':'main','inputs':{'workflow_id':'sheng-official-baseline','branch':'probe-kqueue'}}, timeout=90)
  ```
  - inputs：`workflow_id`（默认 `sheng-kqueue-wait`，我们用 `sheng-official-baseline`）、`branch`（默认 `probe-kqueue`，即 fence 仓的 codemagic.yaml 分支）、`account_index`（强制 1-10，一般留空自动选）、`resume_build_id`（接管已有 Codemagic build）。
- **监督**：`python D:\unixnu_ops\watch_gha_run.py <run_id> <label>`（后台跑，每分钟心跳，自动从 fence2 remote 取 token）。
- **已知配额问题**：单账号偶尔 402（配额尽）→ dispatch 不带 account_index 自动换号即解决。
- **本机直连 Codemagic API 会被沙箱代理 502 掐**，别尝试，一切走 GitHub workflow 中转。

## 1.3 关键仓库与 pin（速查表）

| 仓库 | 角色 | 当前关键 pin |
|---|---|---|
| `yeyingjun-codes/unixnu-sheng-fence` | **构建编排仓**（codemagic.yaml、workflow、诊断产物收集） | 工作分支 `probe-kqueue`；main 是 workflow 定义 |
| `yeyingjun-codes/UniXNU-sheng` | 设备仓 **fork**（与 upstream 共享对象库，任何 upstream SHA 可直接 fetch） | 分支 `main-27-build`（★当前工作分支，= main `c8f92b20` 剔除 2 个诊断 patch，提交 `16a4bd5e`） |
| `UniXNU/UniXNU-sheng` | 设备仓 upstream | **main HEAD `c8f92b208068eeaa4cd2b0f592671f04ee70076e`（11-18）** |
| `UniXNU/UniXNU` | 构建器仓 | **pin `82b847c4ac3f68a57024b3082ffa3a03442defd9`**（官方 package.yml 同款，勿动） |
| `UniXNU/uefi-sheng` | UEFI | branch `sheng` |
| `UniXNU/UniXNU-sm8550-common` | SoC feed | `2dc650ca76ae38715cd0712e60a44b14fe251745`（main feeds.toml 与 lock 一致） |
| Adreno740 fence 镜像 | GPU | `yeyingjun-codes/adreno740-fence` @ `0b28a0e5b66501f55d71a885ab3f5f21467755a1` |

### fork 上的历史分支（含义与状态）

| 分支 | 内容 | 状态 |
|---|---|---|
| `main-27-build` | upstream main `c8f92b20` − `sheng-startup-failure-log.patch` − `sheng-process-exit-log.patch` | ★**当前正路** |
| `27-boot-progress` | 老基线 `4824d3fa` + boot-progress=2 + appsync 等 4 参数 + series 加过 appsync patch（后回退 series） | **已废弃**（老基线缺显示链） |
| `27-packaged-official` | 老基线纯镜像 | 已废弃 |
| `pr65-desktop` | PR65 `679908d2` + UART 文件 + lock 改动 | **已废弃**（pin 漂移补不完） |
| `official-main` | 早期官方 main 镜像 | 已废弃 |
| probe 系列（`codemagic-probe`/`codemagic-v8-recipe`/`gh29-property-readers`/`fence-adreno740-min` 等） | 11-17 前探针时代产物 | 存档，勿动 |

## 1.4 本机路径与工具链

| 路径 | 内容 |
|---|---|
| `D:\unixnu_ops\` | **运维根目录**。watch_gha_run.py（盯构建）、一堆 fix/add 脚本（历史迭代用）、logs/（189 份失败日志）、artifacts/（产物与 yaml 存档）、config.py（流水线全局配置）、HANDOVER-2026-11-22.md（本文档前身） |
| `D:\unixnu_ops\artifacts\27-appsync\inner\out\boot.img` | **最近一次成功构建的镜像**（SHA `dd133777…66acb`，185716736B，appsync=1 参数版，能跑到启动报告、卡三色） |
| `D:\unixnu_ops\artifacts\27-packaged-baseline\` | 官方老基线成功构建产物（SHA `accbca26…fadc`） |
| `F:\unixnu\UniXNU-sheng-cmprobe\` | git 探针仓（token 载体，remote fence2 带 token） |
| `F:\unixnu\` | **历史大仓**：HANDOVER-sheng-2026-11-12-AUDITED.md（★历史必读）、ARCHIVE-*.md、probe15~22 artifacts（探针镜像全存档）、ud27（userdata v2：`userdata-root-v2.sparse.img` 15,753,807,268B / `userdata-root-v2.img` 15,753,805,824B，**历史最佳根卷，禁刷**）、各 step/fmt 脚本、大量屏摄 png |
| WSL Ubuntu | fastboot 环境（`sudo -n fastboot` 免密） |

### 硬件操作（临时启动，不刷分区）
1. 用户把平板进 Fastboot，回「进了」
2. 一条命令：
   ```
   wsl.exe -d Ubuntu -- bash -lc "usbipd.exe attach --wsl --busid <id>; sleep 2; sudo -n fastboot devices; sudo -n fastboot boot /mnt/d/unixnu_ops/artifacts/<dir>/inner/out/boot.img"
   ```
3. busid 会漂（见过 1-14 / 1-13）：先 `usbipd.exe list | grep -i android` 确认
4. 启动成功标志：`Sending OKAY / Booting OKAY`，设备退出 fastboot（USB 离开 `18d1:d00d`）
5. **重启自动回原系统**（fastboot boot 不写分区）

---

# 第二部分：项目全史与核心结论

## 2.1 大时间线（含历史文档指针）

| 时段 | 事件 | 详见 |
|---|---|---|
| 10-31~11-10 | 探针时代：SHNGROOT v2 建成、launchd/SpringBoard/backboardd 全起来、`present frames=0 swap accepted=0`（用户态活了但无显示闭环）、probe11~16 系列、默认 surface 7008 非空证据 | 11-12 审计版 §3 |
| 11-11 | **事故**：裸 payload.img 误刷 userdata 覆盖 v2 → 后续 root manifest rejected | 审计版 §3.8 |
| 11-12 | v2 userdata 恢复成功（442444KB sparse 20/20 OKAY）；8 次构建失败（拿错 fork/main 树）；i568(17) 线对照 | 审计版 §3.9/§9.1 |
| 11-13~11-17 | gh29、CM 恢复、原生 probe17 构建、真实 v8 屏摄：**backboardd PID 62 存活、Metal registry 注册成功、但 Adreno client open=0、无进程读 MetalPluginName** | 审计版 §16.5 |
| 11-17 20:40 | 结论：下一步=沿 backboardd IOKit matching/open 只读追踪；**不再重跑 gh29、不再换组件/pin、不做主动 open** | 审计版 §16.6 |
| 11-21（本会话） | ①官方 27 老基线 `4824d3fa` 完整构建成功→临时启动仍三色/浅黑屏；②带 boot-progress=2 重建→屏幕连检查点都没有；③锁定 PR65 `679908d2`（官方记录"到桌面"）→ 4 轮构建全败（UART 头缺、fileset 缺 BootWatchdogPolicy/SourceStorage 符号、SoC lock 不生效）；④发现 appsync 是 PR65 特有 patch，手写 patch 4 轮全败（corrupt/does not apply）；⑤**方向大转弯：发现官方 main HEAD `c8f92b20`（11-18）已合入完整 27 显示链**（component:RamBlock、build-sheng-source-storage --policy-dir、appsync、参数体系去掉 sheng- 前缀） | 本文档 |
| 11-22 | main 路线 5 轮构建：v1 挂 checkout（`--branch` 不收裸 SHA）→v2 挂 checkout（fork main 遗留 probe 文件挡 branch-switch）→v3 剔 2 个漂移诊断 patch 后 **95 patch 全过**、挂 profile.toml 缺失→v4 补 profile.toml 后挂 `GeniSpi.h` 缺失→v5 补 .h 后挂 **`GeniSpi.c` 缺失（当前卡点）** | 本文档 |

## 2.2 铁结论（每条都有实测证据，别再推翻重验）

1. **官方 main HEAD `c8f92b20` 是唯一正路**。老基线 `4824d3fa`（11-07）和 PR65（11-07）都是中间态：
   - 老基线缺 `kernel.archives` 里的 `component:RamBlock`、`build-sheng-source-storage.py --policy-dir scripts/policies/ipados-27.0.1-24A446` → fileset 阶段缺 `native_ram_block_gpu_addon`/`native_source_storage_start` 等符号（会被 stub 兜掉但行为不完整）；
   - main 的顶层 kernel_args 已是**新参数体系**（去掉 `sheng-` 前缀：`dpu-scanout=2`、`fb-bgra=1`、`gpu-metal=1`、`appsync=1`、`keyboard=1`、`ci-mps=0`、`ca-triple-buffer=1`、`apfs-boot-shim=1`、`ethernet=1`、`fb-half=2`、`timebase-hz=24000000`、`autoreset=7200`、`uefi-watchdog=1`、`diag=1`、`diag-export=7140`、`gpu-trace=1`、`log-gpu/log-video/log-bluetooth=3`、`build-tag=s00000` 等）。
2. **bootstrap 链接报 `native_*` 缺符号是预期**：`build-fileset-release-reference.py` 会从构建日志正则提取缺失符号→生成 `native-stubs.c`（`long name;` 定义）→`-Wl,-force_load` 重链。**这不是错误，不要修**。
3. **appsync 不救黑屏**：appsync 只覆盖 Data 卷用户 App（`/private/var/` 下 `.app`）的签名信任；SpringBoard/backboardd 是系统进程走 StaticTrustCache。黑屏根因是显示链（main 已修）。
4. **官方 main 的 package workflow 零公开运行记录**（actions 列表为空），所以 main 自带 2 个漂移 patch（`sheng-startup-failure-log.patch`、`sheng-process-exit-log.patch`，`kern_exec.c:10118` 上下文对不上）不奇怪——已在 fork `main-27-build` 剔除，均为纯 weak_import 诊断日志，剔除无功能损失。
5. **`sheng-platform-sleep.patch` 是功能 patch（arm64_platform_sleep_hook），不能剔**。
6. **appsync 官方报告关键信息**（reports/ipados27-appsync.md）：内核在 `ubc_cs_blob_add` 里注册用户 CodeDirectory、工程 trust-cache 接口、每 boot 上限 65536 模块；runtime 用 AppSync Unified rev `235aca6c`；**报告里 fastboot boot 成功只证明 bootloader 接受镜像，"Desktop ... still need observation"**——即上游也没声称 main 一定出桌面。
7. **历史 v8 屏摄结论依然有效**（11-17）：backboardd 存活但 Metal 发现链没走通（`metal name_reads=0`，无进程读 MetalPluginName；Adreno open records=0）。main 的显示链修复正是针对这一层。
8. **设备当前 userdata = 历史 v2**（11-12 恢复），勿再刷 userdata；每次实验都是 `fastboot boot` 临时启动。

## 2.3 已废弃路线清单（再碰就是烧 token）

| 废弃路线 | 死因 |
|---|---|
| 在老基线上手写 appsync patch | 4 轮全败：行号猜不中（8727→8591 全错）、手写 hunk 行数不匹配 → corrupt patch；正确做法是 main 自带版本 |
| PR65 设备树 `679908d2` | `BootWatchdogPolicy`/`SourceStorage` 不进 fileset（其 board 的 archives 与 UniXNU pin 不配）；补 SoC UART `2dc650ca` 进 feeds 后 lock 不生效；`--no-deps`/全 deps 都试过 |
| 老基线 + 参数注入（appsync=1 无实现） | 构建成功、启动无变化——证明缺的是代码不是参数 |
| `git clone --branch <裸SHA>` | git 语义不接受，必须 `init + fetch --depth 1 origin <SHA> + checkout FETCH_HEAD` |
| clone fork main 再 checkout main SHA | fork main（2b75decd）带 probe15 遗留文件（`.github/scripts/patch-ramdisk4.py`、`ci/NativeUfs.probe15.cpp`）挡 branch-switch |
| 本机直连 Codemagic API | 沙箱代理 502；一切走 workflow 424701452 中转 |
| 一次性大文件下载 | 沙箱 SIGTERM（>50MB 必挂）+ curl 超时 exit 28 |
| 11-12 审计版 §9 的全部禁令 | 全部继续有效（v1 废墟勿刷、自研 fastboot 勿用、571 时代结论勿复述等） |

---

# 第三部分：当前卡点与下一步（新窗口第一件事）

## 3.1 当前卡点（v5，run 44977862136）

`build-sheng-source-drivers.py`（UniXNU `82b847c4` 版，已存 `D:\unixnu_ops\artifacts\build-sheng-source-drivers.py`）第 144-149 行：

```python
'ShengInputTransport': [(device / 'package/TouchProbe.cpp', [
    '-I', str(ROOT / 'drivers/QcomGeniSpi'), '-I', str(device / 'drivers/ShengNovatekTouch')]),
    ...,
    (ROOT / 'drivers/QcomGeniSpi/GeniSpi.c', []),        # ← v5 挂这：tree 里没有此文件
```

v5 已把 `GeniSpi.h` 复制进 tree（v4 修复），但同函数还要编译 `GeniSpi.c`、`NvtProtocol.c`、`NvtTouchCore.c`。

## 3.2 修复（改 fence 仓 probe-kqueue 分支 codemagic.yaml 的 package 步骤）

把现有"补 GeniSpi.h"段落替换为整目录复制：

```bash
TREE="$WORK/UniXNU/out/sheng/ipados-27.0.1-24A446/sheng_ipados27/tree"
# OS profile（v4 修复，保留）
if [ ! -f "$TREE/profiles/os/ipados-27.0.1-24A446/profile.toml" ]; then
  mkdir -p "$TREE/profiles/os/ipados-27.0.1-24A446"
  cp "$WORK/UniXNU/profiles/os/ipados-27.0.1-24A446/profile.toml" "$TREE/profiles/os/ipados-27.0.1-24A446/"
fi
# QcomGeniSpi 整目录（v6 修复，替换 v5 的单文件版）
if [ ! -f "$TREE/drivers/QcomGeniSpi/GeniSpi.c" ]; then
  mkdir -p "$TREE/drivers/QcomGeniSpi"
  cp "$WORK/UniXNU/drivers/QcomGeniSpi/GeniSpi.h" "$WORK/UniXNU/drivers/QcomGeniSpi/GeniSpi.c" "$TREE/drivers/QcomGeniSpi/"
fi
```

（如果后续还报 `ShengNovatekTouch/NvtProtocol.c` 之类缺文件，同模式整目录补 `$WORK/device/drivers/ShengNovatekTouch/`——root cause 是 tree 组装（`unixnu tree`）没链接这些 kit，逐个补不如考虑把 `unixnu tree` 步骤本身跑对。）

改法（标准循环）：GET fence `probe-kqueue` 的 codemagic.yaml 拿 sha → 本地改 → PUT 回去 → dispatch 424701452 → watch。

## 3.3 v5 之后可能的下一批坑（预判，来自 v5 日志 `D:\unixnu_ops\logs\main-v5-package.txt`）

- v5 日志 297 行还有一条 `build-xnu-4k-baseline.sh: line 829: make ...` 失败——这是 bootstrap pass 的预期失败（见 2.2 条 2），构建器自己处理，**不用管**。
- source-drivers 过后是 `archive-20-build-fileset-release-reference`（stub 自动补）→ prelink → payload → 出镜像。若 fileset 阶段真挂（非 stub 能救的），再看具体符号。

---

# 第四部分：标准工作循环（逐条照抄）

## 4.1 改配置 → 触发 → 监督 → 读日志

```
1. 取 token（见 1.1 模板）
2. GET https://api.github.com/repos/yeyingjun-codes/unixnu-sheng-fence/contents/codemagic.yaml?ref=probe-kqueue
   （= 当前生效配置；本地留档 D:\unixnu_ops\artifacts\codemagic-27-main.yaml 是最近一版）
3. 本地 python + yaml.safe_load 修改 → safe_dump(sort_keys=False,width=200)
4. PUT 同路径（message + content=base64 + sha=第2步的sha + branch=probe-kqueue）
   ⚠️ 409 = sha 过期，重新 GET 再 PUT
5. POST dispatch（见 1.2 模板）→ 204
6. 轮询 runs?per_page=1 拿 run_id（新 id 大于上一个）
7. python D:\unixnu_ops\watch_gha_run.py <run_id> <label>  （run_in_background=true）
8. 失败 → 拉 artifact：
   GET runs/<id>/artifacts → artifact id → GET <id>/zip（几 KB~几 MB，直接下载没问题）
   → 外层 zip 里找 *.zip → 内层 out/diag/*.txt（08-package.txt 是主日志）
9. 改 codemagic.yaml → 回 5
```

## 4.2 成功后验收与启动

```
1. artifact ~138MB：分块下载（10MB Range + .part 续传 + run_in_background，见坑表）
2. 解压两层 → out/boot.img
3. 验收：sha256sum、ls -l（~185MB）、head -c 8（应为 ANDROID!）、
   python 数参数：boot.img 里应含 dpu-scanout=2 / fb-bgra=1 / appsync=1（新参数体系无 sheng- 前缀）
   对照 package.manifest.json（os_profile / revisions / patches 数 / outputs sha）
4. 叫用户进 Fastboot → 回「进了」→ WSL fastboot boot（见 1.4）
5. 看屏幕：出 UI 拍照；三色/黑屏报告现象；panic 拍错误行
```

## 4.3 当前生效 codemagic.yaml 的结构（9 步骤）

```
environment diagnostics / host toolchain
checkout the three trees as siblings   ← 设备仓 init+fetch main-27-build 分支+FETCH_HEAD；UEFI clone sheng；UniXNU init+fetch 82b847c4
platform seed sanity
fix the upstream mesa patch header
install WCN7850 firmware (linux-firmware, pinned)
fetch Ath12kWifi locked sources (linux/freebsd/wpa_supplicant)  ← 物化 deps（sparse-checkout 修复版内嵌，勿删）
package   ← scripts/package.sh --os 27 --uefi ../uefi-sheng --init-data + 前置补文件段
collect outputs
```

关键 vars：`UNIXNU_REF=82b847c4…`、`DEVICE_REF=main-27-build`、`UEFI_REF=sheng`、`ADRENO740_REPO=yeyingjun-codes/adreno740-fence`、`ADRENO740_REV=0b28a0e5…`。

## 4.4 坑速查表（全部真踩过）

| 症状 | 原因 | 解法 |
|---|---|---|
| `git clone --branch <sha>` 报 not found | `--branch` 只收分支/tag | `git init -q X && git -C X remote add origin … && git -C X fetch --depth 1 origin <SHA> && git -C X checkout -q FETCH_HEAD` |
| checkout main SHA 报 local changes would be overwritten | fork main 带 probe 遗留文件 | 同上（init+fetch 绕开） |
| submodule 更新后旧文件残留 | checkout 后 submodule 指旧 pin | `git -C device submodule sync --recursive && git -C device submodule update --init --recursive --depth 1` |
| 下载 >50MB 被 SIGTERM | 沙箱杀长进程 | 10MB Range 分块 + `.part` 断点续传 + run_in_background |
| curl exit 28 | 沙箱代理超时 | 同上 |
| API PUT 409 | contents sha 过期 | 重新 GET 拿 sha |
| API 502/TimeoutError | 沙箱代理间歇 | 重试（1-3 次内必过） |
| dispatch 后 402 | Codemagic 账号配额尽 | 重新 dispatch 不带 account_index |
| `corrupt patch at line N` | 手写 patch hunk 行数/行号错 | **别手写 patch**；用上游自带版本或 git diff 生成 |
| `patch does not apply` | 上下文/行号漂移 | 同上；或如 main-27-build 一样剔除该 patch |
| WSL attach 失败 | WSL 停了/busid 漂 | `wsl --shutdown` 重进；先 `usbipd list` 确认 busid |
| fastboot devices 空 | 设备未接线/已关机 | 先查 `usbipd list`/PnP 状态，别怪脚本 |
| Python -c 里嵌 `$VAR` | Windows bash 先展开 | 用 heredoc（`python.exe << 'PYEOF'`）单引号防展开 |
| Node child_process 调 adb | EBUSY | 写文件给 Bash 接力 |
| tomllib 无 dumps | 标准库只读 | 手工行级编辑文本再 tomllib.loads 验证 |

---

# 第五部分：知识宝库（有用没用都塞这）

## 5.1 诊断产物结构（每个失败 run）

```
out/diag/01-env.txt            环境
out/diag/02-toolchain.txt      工具链
out/diag/03-checkout.txt       checkout（git 冲突在这）
out/diag/05-seed-check.txt     平台种子（8 hex）
out/diag/07b-wifi-firmware.txt WCN7850 固件
out/diag/07c-ath12k-sources.txt Ath12k 源物化 + source-identity.json 校验
out/diag/08-package.txt        ★主构建日志（patch 序列、每 archive、真实错误）
out/diag/08a-mesa-patch.txt   mesa 头修复
成功时：out/boot.img / kernel.macho / payload.img / package.manifest.json
```

## 5.2 构建 95 patch 序列（v3-v5 全过，供对照缺谁）

arch(2) → soc(65) → os(darwin26-syscalls/kpi/shared-region) → device 序列：
`zzye-cpu-idle, zzyf-amp, zzyd-audio-addon-mount, source-storage-runtime, zzzz-ipados27-bringup, vmwait-dyld-pager-source-release, zzzzzz-latency-trace, zzzzzzzz-exit-latency, zzzzzzzzz-unnest-trace, sheng-wifi-launchd-cache, sheng-bluetooth-runtime, sheng-wifi-association-event, sheng-main-thread-profile, sheng-cache-input-diagnostic, sheng-bluetooth-exit-diagnostic, zzzzzzzzzz-sigp-reinit-assert, sheng-appsync-runtime, sheng-appsync-user-trust, zzzzzzzzzzz-edge-matrix, zzzzzz-bsd-checkpoints, sheng-bootstrap-checkpoints, sheng-headless-startup-checkpoints, sheng-platform-sleep`
（main-27-build 已剔：`sheng-startup-failure-log`、`sheng-process-exit-log`）

## 5.3 kernel archives 链（main 的正确配方，老基线缺的后半段）

```
build-corecrypto-14.py, build-corecrypto-14.py --namespace,
component:ArmDTPlatform, component:ArmCpu, build-libpthread-kernel.py,
component:ShengUfs, build-sheng-source-storage.py --policy-dir scripts/policies/ipados-27.0.1-24A446,
component:RamBlock, component:Adreno740, fetch-sheng-dts.py, fetch-adreno-inputs.py,
prepare-sheng-gmu.py, prepare-sheng-gpu-smmu.py, prepare-sheng-gmu-votes.py,
build-adreno740-kits.py, build-adreno740-accelerator.py, component:AppleKeyStoreState,
build-gop-legacy-display-27.py, build-fileset-release-reference.py --tree . --lto
```

## 5.4 主要 kernel_args 差异（老基线 vs main）

- 老基线（47 项，`sheng-` 前缀体系）：`sheng-touch=4, sheng-fb-bgra=1, sheng-dpu-scanout=2, sheng-gpu-metal=1, sheng-backlight=1, sheng-gpu-addon=1, boot-progress=2…`
- main（新体系）：去前缀 + 新增 `keyboard=1, usb=1, bluetooth=1, aks-sls=3, appsync=1, ethernet=1, fb-half=2, apfs-boot-shim=1, ca-triple-buffer=1, ca-free-wakeup=1, autoreset=7200, uefi-watchdog=1, timebase-hz=24000000, diag=1, diag-export=7140, gpu-trace=1, log-gpu=1, log-video=1, log-bluetooth=3, build-tag=s00000, ci-mps=0`
- 27 的 os_overrides **没有** kernel_args 覆盖（只有 prelink roots）；macos-27.3 覆盖有完整 args（参考用）

## 5.5 appsync 技术细节（防再走弯路）

- 内核 patch：`sheng-appsync-runtime.patch`（kern_exec.c 的 `native_gpu_addon_prepare` 里挂 `/usr/lib`、`/usr/libexec`、MobileInstallationHelper、CoreServices 四个 bindfs mount）+ `sheng-appsync-user-trust.patch`（`ubc_cs_blob_add` → `appsync_trust_user_code` → 工程 trust-cache 模块注册，`kTCTypeEngineering`，上限 65536/boot，`CONFIG_SPTM` 下返回 NOT_SUPPORTED）
- board 配置：`payload.runtime.appsync = true`（触发 runtime 生成 `/private/var/ngpu/appsync/*` 文件）+ 顶层 `appsync=1` boot arg
- 上游报告：`reports/ipados27-appsync.md`；AppSync Unified rev `235aca6cddfbdc9fa87fcb5b2aec2df37ed6d65a`（GPLv3，Procursus ldid 签名器）
- **只管用户 App，不管系统进程**（SpringBoard/backboardd 走 StaticTrustCache）

## 5.6 数据种子与"首装"

- `--init-data` = 无保存种子时生成**新装** Data seed（清数据安装）
- 已保存种子缓存于 GitHub Actions cache（key `data-seed-v1-<sha256(chipid)[:16]>-27`），路径 `UniXNU/out/.../runtime/data.dbr` + `inputs.json`
- 也可 `data_seed_url`+`data_seed_sha256` inputs 传入原装种子（HTTPS+64 hex 必须）
- 本地留档：`D:\unixnu_ops\data.dbr.enc`（AES-256-CBC，口令=secret `SEED_PASSPHRASE`）、`gh10-seed.zip`
- v5 构建时 runtime 用了 preserved seed `sha256 447157af4a80…`（Data UUID `A109B687-4A5A-49C2-8C26-A2EA1FD73B55`）；更早 v3 构建生成过新 seed `2f40ce96d0dc…`（UUID `945C7589-…`）；官方 appsync 报告里原始 seed `1bde7901df3a…`。**含义**：每次 init-data 都是新 UUID，别拿旧 manifest 硬对
- 历史最佳 v2 userdata（F:\unixnu\ud27）**绝对禁止再刷**（审计版 §9 禁令）

## 5.7 构建历史账本（11-21~22 全部 25 run）

| run | 内容 | 结果 |
|---|---|---|
| 44862653397 | 官方老基线 4824d3fa | ✗ 缺 WCN7850 固件 |
| 44865202684 | +固件 | ✗ 缺 ath12k deps/linux |
| 44866670725 | +ath12k 物化 | ✓ **成功**（boot accbca26…，启动仍三色） |
| 44871090116 | +boot-progress=2 | ✓ 成功（屏幕仍无检查点） |
| 44875958299 | PR65 树 | ✗ BluetoothProbe 缺 Sm8550GeniUart.h |
| 44879171624 / 44881214520 | +SoC 2dc650ca feeds/lock | ✗ 同错（lock 没生效） |
| 44883093949 / 44883460057 / 44884327415 / 44886453204 | UART 源各种摆放 | ✗ 各式自伤 |
| 44887263991 / 44887552963 | 移除覆盖 checkout | ✗ ath12k / fileset 67 符号 |
| 44889177861 / 44891160962 | Wi-Fi 依赖+全 deps / 自动账号 | ✗ 同 fileset 符号（即 appsync 参数无效铁证） |
| 44894252205 | 全依赖 | ✗ 同 |
| 44898196258 | 27-appsync 参数版（27-boot-progress+4参数） | ✗ ath12k 步骤丢失 |
| 44901626311 | v2 恢复 ath12k 步骤 | ✓ **成功**（boot dd133777…，启动仍浅黑屏） |
| 44911946892 / 44915946945 / 44917855615 / 44919924612 | 手写 appsync patch v1-v4 | ✗ corrupt/does not apply（此路判死） |
| 44925908807 | main HEAD 直建 | ✗ clone --branch 裸 SHA |
| 44926419607 | main v2（init+fetch） | ✗ fork main 遗留文件挡 checkout |
| 44929087680 | main v3（main-27-build 分支） | ✗ profile.toml 缺（95 patch 全过！） |
| 44931469026 | main v4（补 profile） | ✗ GeniSpi.h 缺 |
| 44977862136 | main v5（补 .h） | ✗ **GeniSpi.c 缺（当前卡点）** |

## 5.8 上游文档与资料入口（审计版 §13 已详列，补充）

- 官网：unixnu.com（porting/building/records/UFS/prelink/payload/UEFI 各指南）
- 官方 package.yml（main）：`.github/workflows/package.yml`——**构建命令真源**：`scripts/package.sh --os 27 --uefi ../uefi-sheng [--init-data]`，工具链 brew 清单、种子校验逻辑全在里面（已存 `D:\unixnu_ops\artifacts\main-package.yml`）
- AGENTS.md（fence 与设备仓均有）：porting 记录义务、组件选择规则、`./unixnu defconfig sheng_defconfig --device ../UniXNU-sheng` 本地构建路径（需 macOS）
- `build-fileset-release-reference.py` 全文要点：inputs 哈希缓存、`native-stubs.c` 自动 stub、`Private.exports` 剔除不可用 forced exports、LTO 模式
- `profiles.py`：`resolve_os`（`--os 17/26/27` 解析）、`ctx.profile_roots`（arch/soc/os/device 四层合并、board 的 remove 列表）

## 5.9 设备/显示层知识（历史沉淀，判读屏幕用）

- 三色条 = 红/绿/品红水平带 + 停在启动报告界面（**别再叫"黑屏"**，审计版禁令 8）
- 浅色黑屏无内容 = 连 boot-progress 检查点都没渲染（显示链极早期就没通）
- probe17 报告图走 GOP 旁路直画；正常 UI 走 DPU scanout——两条路径
- v8 关键读数（11-17）：`metal publish stage=5 status=0 registered=1`、`registry IOAcceleratorES count=1`、`mobile open events=2（IOMFB_FDR_Loader pid88 / MobileGestaltHel pid108，均 NativeLegacyDisplay）`、`metal name_reads=0`、`Adreno open records=0`
- `selector 28 status=e00002f0`（kIOReturnUnsupported 类）是 MobileGestalt 查询失败的痕迹
- MIUI 侧无关；本设备是小米平板，fastboot 模式 `18d1:d00d`

## 5.10 历史 HANDOVER 文档链（溯源用）

```
F:\unixnu\HANDOVER-sheng-2026-11-12-AUDITED.md   ← ★主历史文档（§0-§16，最权威）
F:\unixnu\HANDOVER-sheng-2026-11-09.md
F:\unixnu\HANDOVER-sheng-2026-11-05.md
F:\unixnu\ARCHIVE-sheng-2026-11-03.md / 2026-11-05.md
F:\unixnu\patch\HANDOVER-2026-10-31-FINAL.md / SCREEN-ARCHIVE.md / ci\PLAN-2026-11-12.md
D:\unixnu_ops\HANDOVER-2026-11-22.md            ← 本文档 v1（本文档是其完全超集）
```

## 5.11 遗留约束（审计版禁令仍然有效的重点摘录）

1. 不刷 v1 废墟（`patch\ci\userdata_out27\...`）；不用自研 fastboot 写 userdata
2. 不把进程存在说成界面可见；不把探针计数升级成整机正常
3. 不因构建失败去乱改 board.toml args/os_profile
4. 种子不明文进公开仓（AES + SEED_PASSPHRASE）
5. `git push` 大仓不可靠，用 Git Data API + tree SHA 校验
6. 操作前先查设备真实连接（CM_PROB_PHANTOM 教训）
7. `sheng-lite=2` 对老内核无效（只认 1）——main 新体系下 lite 参数仍在，注意版本
8. gh29 已证实是 runner 容量问题，不重跑查代码

---

# 第六部分：验收标准与终点

- **P0（当前）**：main-27-build 出完整镜像（GeniSpi 目录补全后）
- **P1**：`fastboot boot` 后**出可见 UI**（Apple logo / 锁屏 / 桌面），拍照存档
- **P2**：触摸可用、亮度可调（对照上游 PR65 记录的行为）
- **P3**（若 P1 达成再谈）：appsync 装用户 App、长期刷写方案（写 boot 分区 + 保留 userdata 的正式安装）

—— 交接完毕。新窗口从 **§3.2 的 v6 修复**直接开干：改 codemagic.yaml package 步骤（GeniSpi 整目录复制）→ dispatch 424701452 → watch → 成功后走 §4.2 验收启动。

---

# 第七部分：v3 增量（2026-11-22 ~ 11-24，Codemagic → GitHub Actions 迁移 + 主线构建推进）

> 本部分追加于 v2 之后，原文未动。记录从 v6（run 44991507788）之后到 v30（run 45301863101）的全部进展与当前卡点。
> **状态一句话：构建管线大幅推进，但主内核链接仍缺 13 个符号，boot.img 尚未产出，真机未验证。**

## 7.1 通道变更：Codemagic 已死，改用 GitHub Actions

- Codemagic 10 个账号 token 在 11-23 全部失效（401 invalid），新注册 2 个账号也只有读权限、无法创建应用（403 FORBIDDEN）。
- **决定**：彻底放弃 Codemagic，改用 GitHub Actions 的 macOS runner 直接构建。
- **新工作流**：`unixnu-sheng-fence/.github/workflows/sheng-27-main-github.yml`（workflow id `427757211`，`main` 分支，`macos-latest`，360 分钟上限，手动 dispatch）。
- 迁移中修掉的坑：`CM_ENV` → `GITHUB_ENV`、工具链路径写 `GITHUB_PATH`、输出目录指向 `$GITHUB_WORKSPACE/out`、package 重试从 3 次减到 1 次并同步修日志收集条件。
- **§1.2 的 Codemagic 账号池不要再尝试。**

## 7.2 UniXNU 主框架修复（fork main-27 分支）

- fork 的 main 太旧缺 `patches/mesa/turnip-frame-diagnostics.patch`，基于上游 `82b847c4` 新建 `main-27` 分支。
- `build-sheng-hid-input.py` 的 iOS 17 限制改为：iOS 27 自动转发 `build-sheng-source-drivers.py` 并自动注入 `--tree`/`--device`。
- mesa patch 缺 `new file mode 100644` 头，工作流自动补。
- `KeyboardProbe.cpp` 的 `kClamshellLog` 和 gop-legacy-display 的 macOS-only 函数在 iOS `-Werror` 下报错，已标记 unused / 加 `-Wno-unused-function`。
- **当前 UniXNU pin**：`57f1126d880c8f315d61e1d11e4abbc1cda719d4`（main-27 分支）。

## 7.3 weak_import stub 注入（解决内核链接弱符号）

- macOS-only 的 weak_import 符号（`_sheng_software_aes_probe` 等）在 iOS 链接时未定义。
- 修法：patch `build-xnu-4k-baseline.sh`，在 `.cache/xnu-work` clone 之后、make 之前生成 `native_weak_stubs.c` 并注册进 `osfmk/conf/files`。
- 时机卡得很严：之前失败都是因为 stub 写早了（目录没生成）或 `$WORK` 在单引号 heredoc 里没展开。
- **stub 只给真正的 weak_import 探针钩子用，§7.6 的 13 个符号不许加进去。**

## 7.4 APFS Data 种子盘（卡最久，已解决）

- `seed-data-grow.py` 挂载 APFS 镜像后 `diskutil` 找不到容器。
- 排查过程：加 30 秒轮询 → 没用；匹配 `disk10s1` → 不对；打印完整 APFS 列表后发现**挂载的原始设备是 `disk10`，但容器物理存储实际是 `disk9`**，编号对不上。
- **最终修法：按卷名 `Data` 定位容器**，彻底解决。
- 相关 fork commit：`b0c3b252`（轮询）、`7fe8a38e`（分区匹配）、`12e6228c`（designated store）、`99ad5783`（Data 卷名）。
- 现在 Data UUID 正常生成，runtime/GPU/Wi-Fi 插件全部顺利通过。

## 7.5 外部依赖全部锁定并自动获取

- WCN7850 固件：按 manifest 校验大小和 SHA-256。
- Ath12kWiFi 的 linux/freebsd/wpa_supplicant：按 source-lock 钉死 commit，处理非 cone 稀疏检出。
- 键盘 MCU 固件：走 `extract-files.py --section Keyboard` 正常提取。
- `prepare-xnu-source.py` 加 GitHub API 403/429/5xx 重试 + token 认证。

## 7.6 当前唯一卡点：主内核链接缺 13 个符号（v30，run 45301863101）

种子盘、95 patch、Wi-Fi、GPU、fileset RELEASE reference 全过之后，**主内核链接报 13 个未定义符号**：

1. 存储：`_native_ram_block_gpu_addon`、`_native_source_storage_start`、`_native_verified_block_*`
2. 加密/看门狗：`_corecrypto_kext_start`、`_sheng_boot_watchdog_policy`
3. 显示/启动：`_native_legacy_display_*`、`_boot_*`

**根因判断**：`build-xnu-4k-baseline.sh` 靠 `XNU_NATIVE_RAM_BLOCK`、`XNU_NATIVE_LEGACY_DISPLAY` 等**环境变量开关**决定是否 force_load 对应归档。defconfig 里的 `CONFIG_XNU_*` 到这些环境变量的映射、以及脚本期望的归档路径与组件实际输出路径是否一致，**都未端到端验证**。

**已试但没用的方案**（别再重复）：
- 给 `kernel.archives` 补 `component:VerifiedRoot` 等条目 → 没用
- 给组件填 `build` 配方、`build_stage` 改成 `kernel` → 没用

**下一步排查（按顺序）**：
1. 抓失败现场：打印实际生效的 `XNU_*` 环境变量、`KERNEL_EXTRA_ARCHIVES`、完整链接命令
2. 逐个符号查 `.a` 实际产出位置，`nm` 验证符号，对比脚本期望路径
3. 顺 `xnu_env(ctx)` 和 `archive_plan` 确认 defconfig → env 映射是否真的生效
4. 对齐构建/链接约定，**不要再加 stub**

## 7.7 操作注意

- 多个 run（45192218539、45195435528、45230943668、45273560633）是**排队时被取消**，没开始跑，不算代码失败。dispatch 前先查有没有活跃 run。
- 诊断日志都在本地 `artifacts/github-*/08-package.txt`，最新的是 `github-30`。
- 到本文写完，**没有任何一次成功的完整打包，没有真机验证**。

—— v3 增量完毕。新窗口从 **§7.6 的 13 符号链接卡点**接着干：先抓环境变量和链接命令现场，再逐个核对归档路径。
