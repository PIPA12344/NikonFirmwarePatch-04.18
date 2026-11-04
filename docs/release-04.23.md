# 04.23 构建与验证 / Build and validation

日期：2026-11-04（Asia/Shanghai）。本次为 04.18 的累计开源更新，仓库地址不变。更新内容见 [CHANGELOG](../CHANGELOG.md)。

## 构建

从官方 Z8 C 3.11 输入重新构建，Python 3.10+：

```sh
python -m pip install -r requirements-log3g10-research.txt
python -m z8vaassist.build "/path/to/Z_8_0311.bin" build/my-0423 --version 04.23
python -m z8vaassist.verify "/path/to/Z_8_0311.bin" build/my-0423/Z_8_0423.bin --version 04.23
python -m z8cardwav.verify_staged build/my-0423-card-wav-build
```

输出目录必须不存在。第一条构建包含四项原有功能、两种自定义 Log、卡内 WAV 和 View Assist；不是只更改版本号。默认使用仓库内的预编译单元，均有哈希校验，不需要编译器。卡内 WAV 旧单元 resources/cardwav.bin 对应 04.18，新单元 resources/cardwav-0423.bin 对应 04.23，不能互换。

卡 WAV 也可通过 z8cardwav.builder 的 code_source='source' API 编译，编译器为 LLVM/clang 19.1.5，路径由 Z8_LLVM_BIN 指定。源码模式仍须匹配相应资源清单；不同编译器不能绕过哈希检查。中间开发版本没有随本次提供独立的预编译单元。

标准配方输出：

```text
3c8681ca6bfc9befd1c7a8a1356529954d83606fdc789a4005af9609e8abcdd6  Z_8_0423.bin
```

## 使用变化

- 在 H.265 10-bit 下选择 Log3G10 / RWG 或 S-Log3 / S-Gamut3。Log3G10 名称已去掉 test；文件类型页名称随选择更新。
- 自定义 Log 的 View Assist 使用专用曲线与矩阵，目标是模拟相同场景下原厂 N-Log 的辅助显示；LCD/EVF/HDMI 的真实颜色与输出映射未完成全面实机资格验证，不能据此判断记录素材的颜色正确性。
- WAV 的格式、存放路径与选择方法见 [卡内 WAV 说明](card-wav.md)。04.23 在两份未发布的暂存内确认完整 PCM 与元数据，所有原生 WAV 读取使用独立对齐 IO 缓冲；确认、复制回读和绑定全部通过后才发布。
- 持续差异显示 WAV diff XX @XXXXXX；复制维护后差异显示 WAV copy diff - retry。错误不会被视为有效音频；失败或 BUSY 不耗永久缓存槽。
- 每次开机最多 20 种已成功缓存的声音。每项保留 288000 字节，20 项约 5.76 MB；短 WAV 比旧版更占内存，池不足仍拒绝导入。

## 验证范围

公开源码与新预编译单元重建的整包 SHA256 与已交付并测试的 04.23 完全相同；新单元编译后填入原厂指令的代码，也与当时测试的代码逐字节相同。04.18 的历史构建哈希继续保留。

- 离线：封包 SHA1/CRC、模块边界、配方重建；16 个 VA 门控、160 个矩阵选择、160 个曲线选择、4 个菜单文字场景，以及原有 Log 例程仿真。
- ARM：27 项集成加 13 项专项回归。卡、分配器、音频任务和缓存效果使用测试桩；双视图 DMA 案例是合成模型，不证明真实相机的物理根因。
- QEMU：开发记录中的完整 48 步回放，扫描一次、选文件一次即显示 CUS，PCM 与卡内文件及补零一致。模拟器不是相机。
- 实机：2026-11-04，维护者反馈「首次就显示 CUS，第一张无杂音」，仅覆盖此次卡/文件与首次选择/首张情形。其他 WAV、关机恢复、连拍、各输出 View Assist 和全部固件功能未因此获得整体资格验证。

公开验证摘要见 [validation-04.23.json](validation-04.23.json)。原 04.18 的实机与功能记录仍属于该历史版本。构建程序输出的 camera_verified=false 表示离线工具本身没有执行实机测试，与上述独立、有限的用户反馈不冲突。

## 公开范围

上传源码、许可证、说明、独立生成的 VA 表和已清零 10 个原厂指令槽的补丁单元；指令槽在构建时从用户的官方输入填回。旧四项功能单元和 04.18 卡 WAV 单元保留。Release 附件为同一组补丁与 SHA256SUMS.txt。

不上传原厂或修改后的完整固件、解包模块、卡镜像、实拍/音频素材、Ghidra 工程、运行环境、编译器、本地日志或研究数据。输出哈希仅供用户本地复现比较。

English: Build with your own official Z8 C 3.11 using the commands above. The default uses hash-pinned authored patch units and needs no compiler. The generated firmware matches the previously tested 04.23 SHA256. Validation includes bounded Log/VA emulation, 27 ARM integration plus 13 staged regressions and a recorded QEMU single-selection run. The maintainer confirmed first-selection CUS and clean first-shot audio for the tested card/file only; broader behavior remains unqualified. Only source, documentation and zero-slot patch units are distributed. Experimental firmware remains subject to the existing LICENSE/NOTICE terms.
