# Changelog / 更新日志

## [v04.23](https://github.com/PIPA12344/NikonFirmwarePatch-04.18/releases/tag/v04.23) — 2026-11-04

相对 04.18 的累计更新：

- 新增 Log3G10 / RWG 与 S-Log3 / S-Gamut3 的 View Assist 私有曲线、矩阵和门控；采用原厂 32..992 节点。原厂 N-Log、HLG、SDR 及其他门控条件沿用原路径。
- Log3G10 菜单名称去掉 test；H.265 10-bit 文件类型页随当前选择显示 Log3G10 / S-Log3。
- WAV 导入采用两份独立、未发布的 PCM 暂存，比较完整播放字节及所有格式/长度元数据；诊断哈希相等不能代替逐字节确认。
- 所有 WAV 原生读取先进入独立的 64 字节对齐、4096 字节 IO 缓冲，每次读取前后调用原生缓存维护，再复制实际读取长度。
- 确认通过后准备播放缓冲，并在缓存维护前后读回核对。仅绑定成功后进入不可变内容缓存；确认失败、复制损坏和绑定 BUSY 不占永久槽。
- 保留最多两轮确认、四次完整导入；读取与格式错误不被重试确认逻辑放行。增加 WAV diff 与 WAV copy diff 提示。
- 保留每次开机 20 种内容上限。新实现每个成功缓存项保留 288000 字节分配，最多约 5.76 MB；短 WAV 的内存占用增加，池不足仍拒绝加载。
- 新增 13 项专项 ARM 回归，连同 27 项集成共 40 项；完成封包、限定配方、Log/VA 仿真及 QEMU 单次选择验证。
- 2026-11-04 实机反馈：首次选择显示 CUS、第一张无杂音。仅确认此次卡/文件及首次选择/首张场景，不代表其他 WAV、恢复、各输出 View Assist 或全部固件功能完成实机验证。
- 保留免编译构建：新增清零原厂指令槽的 cardwav-0423.bin 和固定哈希清单；原 04.18 单元与历史配方保留。仍不上传原厂/成品固件、解包模块和本地研究数据。

English: Cumulative update from 04.18. Adds gated custom-Log View Assist with stock 32..992 nodes and matching menu labels. WAV imports use two unpublished PCM staging buffers, aligned native IO with pre/post cache maintenance, full byte/metadata confirmation and immutable publication only after successful binding. Failed confirmation/copy/busy paths preserve cache capacity. Adds 13 staged ARM regressions to the 27 integration scenarios. The tested card/file now shows CUS on the first selection with clean first-shot audio, as reported by the maintainer; broader hardware behavior remains unqualified. A hash-pinned, zero-slot 04.23 patch unit preserves compiler-free builds; firmware images and extracted modules remain excluded.

### 中间开发版记录 / Intermediate development history

- 04.19：引入两种自定义 Log 的 View Assist 选择器与私有表。
- 04.20：View Assist 表改为原厂 32..992 节点。
- 04.21：菜单名称联动，WAV 增加两次完整导入确认。
- 04.22：一致性失败时增加一轮完整确认；实机首次选择仍显示 WAV mismatch - retry，重选可加载，已由 04.23 替代。

中间版本作为开发过程记录，不作为本次独立发布或完整实机验证结论。04.20 的早期归档与后续保存配方原已存在差异，本次未宣称可重现所有早期候选文件。

## 04.18 实验分支 — 2026-11-02

- 非官方分支，基于 v0.3.0-r1，未经原作者审阅。
- 新增 `experimental_log3g10.py`／`z8log3g10/`：H.265 10-bit 色调页加入 Log3G10 / RWG test 与 S-Log3 / S-Gamut3 两行（`--gamut rwg-slog3-dual`），各有私有 Lut1、NlgGamma、色域矩阵、Picture Control 名和取景标签；原厂表保持不变。
- 新增 `z8cardwav/`：s3lemming/z9-firmware-patch 卡内 WAV 快门声的 Z8 移植（GPL-3.0-or-later），由 `--card-wav` 叠加并重新封包。
- `features.py`／`z8prores/package.py` 允许无后缀版本身份（`--no-tag`）。
- 构建与核验入口新增 `--code-source`／`--compiler`；`experimental_log3g10_verify.py` 新增 `--card-wav`；LLVM 目录可用 `Z8_LLVM_BIN` 指定。
- 卡内 WAV 新增预编译模式（默认）：`resources/cardwav.bin` 的 10 个原厂指令位置清零，构建时从输入填回，哈希由 `resources/cardwav.json` 固定，无需 LLVM；`--card-wav-source source` 用 LLVM 19.1.5 编译且必须一致。
- 五个预编译补丁单元随仓库放在 `resources/`（同时作为 Release 附件），哈希固定；`tools/check_repository.py` 只放行这五个与固定哈希一致的 `.bin`。不含 Nikon 固件、解包模块或构建产物。
- 维护者已在 Z8 实机上完成全部验证，包括两个色调行与卡内 WAV 快门声；新增[卡内 WAV 快门声说明](docs/card-wav.md)。

English: unofficial fork of v0.3.0-r1 adding two experimental H.265 tone rows (Log3G10/RWG and S-Log3/S-Gamut3) and the card WAV shutter-sound port. Source and method only; fully camera-verified on a Z8 by the maintainer.

## [v0.3.0-r1](https://github.com/XinmiaoZhao/NikonFirmwarePatch/releases/tag/v0.3.0-r1) — 2026-10-29

- v0.3.0 的第一次主机工具修订，修复 [issue #12](https://github.com/XinmiaoZhao/NikonFirmwarePatch/issues/12)：Windows 的反斜杠路径被误判为源码不匹配。
- 源码身份键统一为 `/`；仍逐字节校验源码与预编译补丁，不改变哈希要求。
- 加入 Windows／POSIX 路径回归、缺失与损坏文件负控，以及 Windows 默认预编译构建检查。
- 四份补丁机器码、15 种组合配方、原厂 C 3.11 输入要求及机内功能均与 v0.3.0 相同。原 v0.3.0 标签与附件保持不变。

English: first host-tool revision of v0.3.0. Fixes Windows source-path comparison by using forward-slash manifest keys, while preserving exact byte/hash checks. Adds cross-platform path regression, integrity negative controls and Windows prebuilt CLI checks. Firmware code, all 15 recipes and the required C 3.11 input are unchanged; the original v0.3.0 tag and assets are retained.

## [v0.3.0](https://github.com/XinmiaoZhao/NikonFirmwarePatch/releases/tag/v0.3.0) — 2026-10-29

- 新增机内像素位移组浏览、选择与 NEFX 合成，支持 4／8／16／32 张无损 NEF 组。
- 新增 FX 3:2 N-RAW 开放门，支持 8.3K 30／25／24p。
- 新增 N-RAW Fine／Basic，形成 High／Fine／Normal／Basic 四档，并提供相应菜单、文件标识与剩余录制时间估算。
- 四个功能选项可独立选择，共 15 种非空组合；ProRes 可与“开放门＋N-RAW”分别构建。
- 改进 RAW 预拍剩余张数：计入 NEF，并随 RAW 压缩、JPEG 档位及 ★ 设置刷新。
- 改进 RAW 预拍的登记拒绝处理：只尝试 JPEG 回退，不再绕过数据库直接写 NEF；后续帧可继续尝试正常 NEF 写入。停止文件机制仍保留。

English: adds in-camera pixel-shift merging, FX 3:2 N-RAW at 8.3K 30/25/24p, four N-RAW quality tiers, and independent selection of four features. Improves pre-capture remaining counts and database-refusal handling; the stop-file mechanism remains in use.

## [v0.2.0](https://github.com/XinmiaoZhao/NikonFirmwarePatch/releases/tag/v0.2.0)

- RAW 连拍／预拍新增 HE★，可在机内“RAW 记录”选择 HE／HE★。
- 移除对 `Z8PRE.CFG` 的依赖，直接使用机内设置；旧配置文件不再读取。
- QUAL／f2、i 菜单和取景画质标识使用普通“画质”设置。
- 完善双卡备份及 RAW／JPEG 分卡规则，每帧使用提交时的主卡槽和副卡槽设置。
- 保留 ProRes 四档与菜单库分别保存功能。

English: adds HE★ RAW capture, removes the CFG dependency, aligns quality controls/displays with the ordinary menu, and extends dual-card routing using the settings stored when each frame is submitted.

## [v0.1.0](https://github.com/XinmiaoZhao/NikonFirmwarePatch/releases/tag/v0.1.0)

- 首次公开面向官方 Nikon Z8 C 3.11 的补丁构建工具。
- 提供 ProRes HQ／Standard／LT／Proxy，支持按拍摄菜单库分别保存。
- 提供 C15／C30 HE RAW 连拍与预拍，使用普通画质菜单选择 RAW／RAW+JPEG／JPEG；NEF 带整幅预览并支持机内回放。
- ProRes 与 RAW 预拍可单独或组合构建。
- 提供源码、预编译补丁工具包和独立固件核验工具。

English: first public release for official Z8 C 3.11, with four ProRes grades, per-bank settings, C15/C30 HE RAW/pre-capture, selectable feature combinations, precompiled patch distribution and independent output verification.
