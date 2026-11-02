# Attribution and license scope

Copyright (C) 2026 NikonFirmwarePatch contributors.

The original tool source and the precompiled patch built from it are licensed under **GPL-3.0-only**; see [LICENSE](LICENSE). This license does not grant rights to user-supplied Nikon firmware. Output licensing depends on its contents, including any generated code; the complete output firmware is not represented as a GPL-licensed distribution. See [GNU's explanation of program output](https://www.gnu.org/licenses/gpl-faq.en.html#WhatCaseIsOutputGPL).

## References and dependencies

- The Nikon package XOR indexing format was studied with reference to [Nikon Hacker's Package.cs](https://github.com/simeonpilgrim/nikon-firmware-tools/blob/main/Nikon-Patch/LocalUI/Package.cs). This repository includes neither that C# source nor its lookup tables. The implementation recovers equivalent parameters from the user-supplied package.
- [Capstone 5.0.7](https://github.com/capstone-engine/capstone/tree/5.0.7) is installed separately to inspect generated ARM64 instructions. Its code and runtime are not bundled here; its license is available in [LICENSE.TXT](https://github.com/capstone-engine/capstone/blob/5.0.7/LICENSE.TXT).
- [Clang/LLVM](https://clang.llvm.org/) is an optional external dependency for explicit native-patch source builds and release preparation. The default Release toolkit uses the reviewed precompiled patch. No compiler or runtime is bundled.

The compatibility profile contains hashes and layout parameters, not firmware contents. The Release toolkit includes the four patch units (pre-capture, pixel-shift main/AF and open-gate) compiled from the corresponding published C/assembly source, plus the complete tool source, build scripts and license. No Nikon input image or complete patched output is included. Other patch instructions are generated from source; menu structures and text are read from the user's input. The release manifest binds the source commit, compiler recipe and individual files.

The screenshots document the firmware interface running in an emulator. The tool's source-code license does not relicense the depicted firmware interface.

`z8cardwav/` is the Z8 port of the card WAV shutter sound from [s3lemming/z9-firmware-patch](https://github.com/s3lemming/z9-firmware-patch/tree/88a6f3e5195d7f38792dc8eddeb1526fde4096dc), GPL-3.0-or-later. Its own LICENSE, NOTICE and source-provenance.json stay with it; the original project does not endorse or qualify this port.

`z8log3g10/` computes its tables from public specifications: the [RED Log3G10 / REDWideGamutRGB white paper](https://docs.red.com/955-0187/PDF/915-0187%20Rev-C%20%20%20RED%20OPS,%20White%20Paper%20on%20REDWideGamutRGB%20and%20Log3G10.pdf), Sony's S-Log3 constants as published in [ACES IDT.Sony.SLog3_SGamut3.ctl](https://github.com/ampas/aces-dev/blob/710ecbe52c87ce9f4a1e02c8ddf7ea0d6b611cc8/transforms/ctl/idt/vendorSupplied/sony/IDT.Sony.SLog3_SGamut3.ctl), and ITU-R BT.2020 primaries. The 229-node grid and grey placement were cross-checked against [ShiSheng233/NLoader-apps](https://github.com/ShiSheng233/NLoader-apps/tree/0912deac4aff767af56f3ebf9b3f093faff35744/log3g10); no code from that project is included. RED, Sony and Nikon do not endorse this experiment.

This 04.18 fork is not reviewed or endorsed by the NikonFirmwarePatch maintainers.

## Contributor acknowledgements

We thank the following contributors, **in no particular order**:

- [@Mei-MingLe (日月)](https://github.com/Mei-MingLe) for research ideas and analysis.
- [@heavensabove (pai)](https://github.com/heavensabove) for the foundational pixel-shift merge work and base code.
- [@y-g-jiang (Jiang Yaogeng)](https://github.com/y-g-jiang) for research ideas and suggestions, and for technical discussions that helped refine the approach.
- [@ShiSheng233 (锂化溴)](https://github.com/ShiSheng233) for open-gate ideas and the implementation framework, and for sharing the related reference implementation.
- [@aoyukkk (傲宇)](https://github.com/aoyukkk), [@South-Bridge (琴岛唯一指定哥布林)](https://github.com/South-Bridge), and “追晚霞的流浪汉” for development assistance, camera testing and feedback.

## Emulator acknowledgements

- [RdWing/z8-qemu](https://github.com/RdWing/z8-qemu): Z8 adaptation used as the basis of the offline camera-model environment.
- [WonderLantern/z9-qemu](https://github.com/WonderLantern/z9-qemu): upstream camera model and supporting tools on which the Z8 adaptation builds.
- [WonderLantern/z7-qemu](https://github.com/WonderLantern/z7-qemu): emulator and protocol-reference work consulted during development.
- [QEMU](https://www.qemu.org/) ([source repository](https://gitlab.com/qemu-project/qemu)): underlying emulation infrastructure.

These are external development tools and references. This repository does not redistribute their source or binaries, claim authorship of their work, or imply that their maintainers endorse this patch. Their respective notices and licenses remain applicable.

## Experimental use and responsibility

The generated firmware is experimental. Building, installing or using it can cause data loss, camera malfunction or permanent damage. Users must assess the risks and decide for themselves whether to install it. To the extent permitted by applicable law, the authors and contributors provide no warranty and accept no liability for data loss, camera damage or other losses arising from this project or its outputs. The limitations and disclaimer supplement the warranty and liability provisions in LICENSE; they do not alter third-party rights.

本项目生成的是测试版固件。构建、安装或使用可能造成数据丢失、相机故障或永久损坏。使用者须自行衡量风险并决定是否上机。在适用法律允许的范围内，作者及贡献者不提供担保，不对由此造成的数据损失、相机损失或其他损失承担责任。以上说明补充 LICENSE 中的无担保与责任限制条款，不改变第三方权利。
