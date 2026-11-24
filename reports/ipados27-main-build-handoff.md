# Sheng iPadOS 27 主线构建交接文档

更新时间：2026 年 11 月 24 日。

这份文档记录从 Codemagic 迁移到 GitHub Actions 之后做的全部构建工作、每一步的实际结果、当前唯一的阻塞点，以及接下来要干的事。

**先说明一件最要紧的事：到本文写完为止，还没有成功产出一份能烧进平板的 boot.img。** 前面所有进展都是构建管线上的推进，不是真机验证。下文把"已经做完的事"和"还没解决的卡点"分开写，不混淆。

---

## 一、这次构建用的仓库、分支、配置

后续接手的人先记住这几条，不然对不上号：

- **构建入口（工作流）**：`yeyingjun-codes/unixnu-sheng-fence` 仓库里的 `.github/workflows/sheng-27-main-github.yml`，workflow id 是 `427757211`，跑在 `main` 分支。用的是 GitHub 提供的 macOS 机器，单次任务上限 360 分钟，只能手动触发。
- **设备树**：`yeyingjun-codes/UniXNU-sheng` 仓库的 `main-27-build` 分支。
- **UniXNU 主框架**：`yeyingjun-codes/UniXNU` 仓库的 `main-27` 分支，当前钉死在提交 `57f1126d880c8f315d61e1d11e4abbc1cda719d4`。
- **UEFI 固件**：`UniXNU/uefi-sheng` 仓库的 `sheng` 分支。
- **必须的密钥**（已在 GitHub 仓库设置里配好）：`GHTOKEN`、`UNIXNU_UNIQUE_CHIP_ID`、`SEED_PASSPHRASE`。这三个值不要打印到日志，也不要写进任何文档。

---

## 二、已经做完的事（每一步都有构建记录佐证）

### 1. 修好了 UniXNU 主框架本身的缺陷

最初 fork 过来的 UniXNU 主分支太旧，缺一个关键补丁文件（`patches/mesa/turnip-frame-diagnostics.patch`），构建一开始就报错。做法是基于上游最新提交新建了 `main-27` 分支，把缺的文件补齐。同时把 `build-sheng-hid-input.py` 里那个"只支持 iOS 17"的限制改掉了：现在遇到 iOS 27 会自动转发给 `build-sheng-source-drivers.py` 处理，并自动带上 `--tree` 和 `--device` 两个参数（之前没传参数导致报错）。

mesa 那个补丁文件的"新建文件"头部信息也缺了一行，已在工作流里自动补上。

### 2. 解决了内核链接时找不到弱符号的问题

XNU 内核里有一些只在 macOS 上才有实现的弱引用符号（比如 `_sheng_software_aes_probe` 这类），在 iOS 构建里链接器会报"未定义"。解决办法是：在 XNU 源码树克隆下来之后、开始编译之前，自动生成一个 stub 文件并注册进编译列表。这个时机卡得很讲究——之前好几次失败就是因为 stub 写早了（目录还没生成）或者路径写错了（`$WORK` 变量没展开，变成了字面字符串）。现在这些问题都解决了。

**注意**：stub 只用来解决真正的弱引用探针钩子。后面要说的那 13 个符号**不是**弱引用，**不能**用 stub 糊过去。

### 3. 从 Codemagic 彻底迁到 GitHub Actions

Codemagic 的 10 个账号 token 全部失效（返回 401），新注册的两个账号也只有读权限、没法创建应用，所以彻底放弃 Codemagic，改用 GitHub 自己的 macOS 机器跑构建。迁移过程中修了一堆环境变量问题：Codemagic 专用的 `CM_ENV` 改成 GitHub 的 `GITHUB_ENV`、工具链路径写进 `GITHUB_PATH`、输出目录指向 GitHub 的工作目录。这些都已经改完并验证能跑。

### 4. 搞定了 APFS Data 种子盘的制作

这是卡得最久的一个问题。制作 Data 种子盘需要挂载一个 APFS 镜像然后扩容，但 `diskutil` 就是找不到刚挂载的容器。排查过程：

- 先怀疑是注册延迟，加了 30 秒轮询等待 → 没用。
- 再怀疑是设备名不对（挂载的是 `disk10`，但实际物理存储可能是 `disk10s1`）→ 还是不对。
- 把完整的 APFS 容器列表打出来一看，才发现真相：**挂载的原始设备是 `disk10`，但 APFS 容器的物理存储实际是 `disk9`**，编号根本对不上。
- 最后改成**按卷名 `Data` 来找容器**，问题彻底解决。

现在种子盘能正常生成，UUID 也正常。后续的运行时组件、GPU 附加模块、Wi-Fi 插件都能顺利构建。

### 5. 补齐了 Wi-Fi 相关的所有外部依赖

- WCN7850 固件：按锁定版本从上游下载，校验文件大小和 SHA-256。
- Ath12kWiFi 需要的 linux、freebsd、wpa_supplicant 三份源码：按锁定提交拉取，并处理了 Git 稀疏检出的兼容问题。
- 键盘 MCU 固件：走正常提取流程拿到。

### 6. 处理了 GitHub API 限流

`prepare-xnu-source.py` 从 GitHub 下载头文件时经常撞 403 限流。现在加了自动重试（遇到 403/429/5xx 会等一段时间再试），并且把 token 传进去用认证请求，限流额度高很多。

### 7. 给组件补了构建配方

`VerifiedRoot`、`QcomGeniSpi`、`ShengNovatekTouch`、`AirNir`、`Ath12kWifi` 这几个组件原来在配置文件里没有实际的构建命令，已补上，并把它们的构建阶段从 `embedded` 改成 `kernel`。**但要说清楚：这一步做了，最后链接还是没通过**，所以这些改动目前只能算"当前状态"，不能算"已验证正确的修法"。

---

## 三、当前唯一的卡点：主内核链接缺 13 个符号

最近一次完整跑完的是第 30 次构建（运行编号 45301863101）。种子盘、补丁、Wi-Fi、GPU 全都过了，**最后在链接主内核时挂了**，报了 13 个未定义符号，分三类：

1. **存储相关**：`_native_ram_block_gpu_addon`、`_native_source_storage_start`、`_native_verified_block_` 开头的几个。
2. **加密和看门狗**：`_corecrypto_kext_start`、`_sheng_boot_watchdog_policy`。
3. **显示和启动进度**：`_native_legacy_display_` 开头的几个、`_boot_` 开头的几个。

### 根因（目前判断）

`build-xnu-4k-baseline.sh` 这个脚本决定要不要把某个组件的归档文件链接进内核，靠的是一组**环境变量开关**（`XNU_NATIVE_RAM_BLOCK`、`XNU_NATIVE_LEGACY_DISPLAY` 等）。而 defconfig 里写的 `CONFIG_XNU_*` 配置项，到这些环境变量的转换过程，以及脚本期望的归档文件路径跟组件实际输出路径对不对得上，**这两件事都还没端到端验证过**。

简单说：组件编出来了，但链接脚本没找到它们。

### 明确不能做的事

**这 13 个符号绝对不许加进 weak stub 文件里。** 它们是需要真实实现的功能符号，不是探针钩子。用 stub 糊过去，内核跑起来就是崩。

---

## 四、下一步要干的事（按顺序）

1. 抓一次失败的链接现场：把实际生效的 `XNU_*` 环境变量、传给链接器的归档列表、完整链接命令都打印出来。
2. 逐个符号查：对应的 `.a` 文件到底生成在哪、`nm` 看里面有没有这个符号、路径跟脚本期望的对不对。
3. 顺着 `xnu_env` 和 `archive_plan` 这两个函数，确认 defconfig 的配置到底有没有正确变成环境变量、组件有没有被真正选中。
4. 把构建和链接的约定对齐。**不要**再往 stub 里加东西。
5. 等干净的构建整条跑通、产出 boot.img 之后，再校验哈希和启动参数，最后才轮到真机 `fastboot boot` 测试。**构建成功不等于能开机**。

---

## 五、操作注意事项

- 好几次构建（比如 45192218539、45195435528 这些）是在**排队阶段就被取消**的，根本没开始跑，这不算代码失败。触发新构建之前先看看有没有正在跑的，别重复提交。
- 别再碰 Codemagic 了，那条路已经死了。
- 所有诊断日志都在本地 `artifacts/github-30/` 目录下，最新的那份就是第 30 次构建的完整记录。
- 到本文写完，没有任何一次成功的完整打包，也没有做过任何真机验证。
