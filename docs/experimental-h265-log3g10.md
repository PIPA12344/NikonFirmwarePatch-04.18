# H.265 Log3G10 / S-Log3 实验

状态：当前版本为 04.18（Log3G10 / RWG 与 S-Log3 / S-Gamut3 双行），**维护者已在 Z8 实机上完成全部验证**。它不是 v0.3.0-r1 原作者发布的功能。下文按开发顺序保留各阶段的离线与 QEMU 记录，其中“仍未完成”等表述是当时的状态。

本仓库只提供方法与源码：不包含 Nikon 固件、解包后的模块、构建产物或可直接刷写的成品。

## 实际改变什么

目标是在机内先对图像应用 Log3G10 编码曲线，再交给 H.265 编码器保存。这里的一维 LUT 是图像处理器表示曲线的数值表，不是监看 LUT、创意调色 LUT 或后期转换。设计路径为：

传感器／原厂线性处理 → 原厂 BT.2020 色彩处理 → 新的 Log3G10 曲线 → 原厂 YCbCr／H.265 10-bit 编码。

实际插入点是 C3.11 原厂 R2Y 任务构建代码的 Lut1 模板选择入口。原生 ARM 指令仿真证明了选择与表复制的行为；没有实拍视频证明整个 ISP 输出已经正确。

视频文件类型的色调子页面新增一行：BT.2020 版本为 **Log3G10 / BT.2020**，RWG 研究版本为 **Log3G10 / RWG test**。原厂 SDR、HLG、N-Log 行和曲线数据都保留。新增行仍向原厂设置系统提交合法的 N-Log 枚举值 2，由独立开关选择新曲线，避免把一个未经固件其他模块识别的新枚举写进持久设置。开关存放在代码中没有引用的原生电影属性 0x03001229（后备字 0xA03D5C0A0，默认 0，同属 0x12 组），通过原生 GUI_SET 写入。

本实验底座为原项目四项功能，可指定其中任意非空组合。`--card-wav` 在此之上叠加卡内 WAV 快门声（`z8cardwav/`，GPL-3.0-or-later，来源见 NOTICE.md；入口为设置菜单 Camera sounds → Type → Load WAV from card），模块因此变长，由 `z8cardwav/stack.py` 重新封包并独立回读。`patch.py` 不接入此实验功能，请使用 `experimental_log3g10.py`。

## 取景器标签

取景画面右上角的 Picture Control 图块由界面控件 0x24（表 0x42AE79A0 偏移 0x120）绘制。原生 N-LOG 是两张 8 位灰度 PNG：编号 0xA7D（64×32 填充）和 0xA7E（68×36 描边），由 0x4041A7DC 选择。

- 0x4041A860 改为按录制任务同一条件选图：开关为 1、文件类型 H.265 10-bit、GUI 色调 N-Log 时用编号 0x1862／0x1863，其余情况保持原生编号。
- 原生图片表 0x431D96D0 只有 0x1862 行且紧邻其他数据，不能追加；钩住查表入口 0x4032DC64，这两个编号直接返回私有 PNG（0x40B0A000）。
- 图片由 `z8log3g10/label.py` 在构建时生成：五个字符全部绘制，字高 24 像素，居中于原厂 26 像素字带，描边由填充图计算。图块文字是 **L3G10**，七个字符放不下。

## 找到的原厂结构

以下是解包 EG 模块的文件偏移，不是完整升级包偏移。必须与 exact C3.11 哈希一起使用。

| 结构 | EG 偏移／入口 | 观察 |
|---|---|---|
| SDR 路径的 Lut1 曲线模板及变体 | 0x4040AB2 | 每行 229 × uint16 |
| N-Log Lut1 三通道模板 | 0x4041010 | 共 1374 字节，三行相同，CRC32 f4b99215 |
| HLG Lut1 三通道模板 | 0x404156E | 紧邻 N-Log 模板 |
| NlgGamma 模板 | 0x4042282 | 四行 229 × uint16，N-Log 行等于 N-Log Lut1 的 12 位四舍五入副本；保持原厂数据 |
| H.265 色调菜单状态 | 0x10B | 原页面共九个物理行，按父页面隐藏；H.265 原来可见三行 |
| 色调页面 | 0x4BCC6C0 | 实验版复制九行并追加第十行 |
| 原生色调入口／确定动作 | 0x4056D384 / 0x4056DA28 | 扩展回调保留原生设置提交 |
| Lut1 选择入口 | 0x4111A4FC | 实验选择钩子 |
| NlgGamma 行选择 | 0x4111A6C0 | 已选行为 1 时按同一条件改用私有表；INFO+0x43 强制第 3 行不变 |
| 原生 M1 重新计算调用 | 0x41116500 | RWG 研究版本在原生计算后组合转换 |
| 原生有符号 3×3 矩阵乘法 | 0x4112CF8C | RWG 使用此原生运算，不替换整个色彩模块 |

原厂 H.265 10-bit 文件类型内部值是 **3**，GUI 的 N-Log 值是 **2**，R2Y 任务的 N-Log 值是 **1**。这些不同层的数值不能混用。

尼康公开规格将 N-Log 配套色域定义为 BT.2020、D65。固件反汇编已定位 R2Y M1 的构建、矩阵乘法及参数传递；这证明了可修改的参数位置，但不能单凭反汇编证明物理 ISP 内部的处理顺序或该处 RGB 已处于线性 BT.2020。RWG 版本因此明确标为研究候选。

## 曲线与色域

新表直接按 RED 公开 Log3G10 公式计算，未经过 N-Log 解码／重编码。229 节点输入网格以及“400 对应 18% 中灰”沿用下述社区研究，并已与原厂 N-Log 表的特征对应；Z8 实拍标定仍缺失。

采用的 15 位表值除以 32 后，黑点约 93.75、中灰线性插值约 341.27。这里是内部 full-range 参考码值，不能直接当成所有 MOV 解码方式下的码值或 IRE。文件电平、RGB／YUV 换算与实拍中灰位置仍需核对。

保留 BT.2020 与使用 Log3G10 曲线在数学上可以配合。后期需要按 **BT.2020 色域＋Log3G10 曲线** 解释。直接按 REDWideGamutRGB＋Log3G10 解释或套要求 RWG 输入的 RED LUT，可能导致色相、饱和度偏差。

RWG 研究版本已把 RED 白皮书的线性 BT.2020→RWG 矩阵写入固件，并在原生 M1 每次重新计算后执行 M_new = T × M_native。T 使用 Q14 定点系数，每行和严格为 16384，以保留灰轴。原生矩阵乘法与参数缩放保持原样。

目标管线是：原厂线性 BT.2020 → RWG 转换 → Log3G10 曲线 → H.265 10-bit。真实硬件上的 M1／Lut1 先后顺序以及输入基色仍缺少实拍证明；不能把此目标描述当作已验证的物理管线。

Lut1 的 12 位副本 NlgGamma 也随之配套：私有表位于 0x40B02600，共 229 个 uint16，值为私有 Lut1 ÷ 8 四舍五入（上限 4092，实际最大 3365）。只有原生已选行为 1（未被 INFO+0x43 强制为第 3 行）、新增开关为 1、文件类型为 3 时使用；原厂四行不修改。这消除了同一任务中 Lut1 为 Log3G10、NlgGamma 仍为 N-Log 的不一致，但不证明 NlgGamma 对像素的具体作用，也不证明它与此前实拍偏暗有关。

转换只在新增选项开启、H.265 10-bit 文件类型和原生 N-Log 任务同时满足时执行。钩子接在“重新计算 M1”的调用处，避免反复序列化同一份参数时叠加 T×T。常规 N-Log、HLG、SDR 保留原生计算。

旧 04.14.e0 候选接在参数序列化处，存在重复组合矩阵的风险，已撤回；当前研究候选身份为 **04.14.e1**。

## 文件元数据

此前 04.14 实拍片段（新增模式，标签沿用原生 N-Log 路径）的 HEVC VUI 与 MOV colr 都标为 BT.709（1/1/1），只有尼康私有 Picture Control 名写着 N-LOG。HEVC／MOV 使用的 ITU-T H.273 代码中没有 RWG，也没有 Log3G10，因此无法写出“RWG／Log3G10”标签。Log3G10 片段改为：

| 位置 | 原生 N-Log | Log3G10 片段 |
|---|---|---|
| HEVC VUI primaries／transfer／matrix | 1／1／1 | 2／2／1（基色、曲线未指定；YCbCr 矩阵仍按原生编码，保持 BT.709） |
| MOV colr nclc／nclx | 1／1／1 | 2／2／1，nclx 的 full range 位不变 |
| Picture Control 名 | N-LOG | LOG3G10 |

矩阵不改为“未指定”：它描述 YCbCr 与 RGB 的换算，补丁没有改变这一步；标为未指定会让解码软件自行猜测矩阵，可能解错颜色。

| 结构 | 主模块 VA | 观察 |
|---|---|---|
| 编码器配置 | 0x402F6C10 | +0x1C0 起依次为 video_format 5、full range 1、primaries、transfer、matrix；w1 为 HLG 请求。钩子在尾部 0x402F72F8 |
| MOV colr 模板选择 | 0x40349A70／0x40349A78 | 跳转到 0x40343D48／0x40343D94，参数 0 为 BT.709，1 为 HLG 9/18/9 |
| N-LOG Picture Control 定义 | 0x440E1250 | 0x110 字节；私有副本只改 20 字节名称。复制处 0x410A8368、查询处 0x410AA7B4 |
| H.265 色调设置存储 | 0xA03D5C124 | 属性 0x0600124A 经原生描述表解析得到；同一方法解析出已用的文件类型地址 0xA03D5C014 |

条件与曲线相同：新增开关为 1、文件类型为 3、GUI 色调为 N-Log（2）；VUI 与 colr 另要求原生 HLG 请求为 0。SDR、HLG、原生 N-Log 和其他 Picture Control 不变。私有模板和定义副本位于 0x40B02900 起。后期仍需手动指定 RWG（或 BT.2020 版本的 BT.2020）＋Log3G10。

## 离线阶段的验证记录

04.18 已由维护者完成实机验证，以下是实机之前的离线记录。

已完成：

- RED 白皮书锚点与全部 229 节点的量化误差检查。
- 原项目全部 15 种功能组合的附加补丁生成、空闲区和旧字符串偏移保留检查。
- 54 个 LUT 路由用例；162 个 Lut1＋NlgGamma 联合路由用例（含 108 个 INFO+0x43 强制第 3 行用例），确认只有 Log3G10 任务使用私有 NlgGamma；216 个原生编码器配置 VUI 用例、216 个 MOV colr 用例和 54 个 Picture Control 用例，确认只有 Log3G10 片段改写标签；36 个菜单入口可见性／标记用例；20 个原生确定动作用例。
- RWG 版本另有 632 个原生 ARM 矩阵用例，检查有符号运算、作用顺序、模式隔离、返回值／寄存器保留及重复调用不叠加转换。
- BT.2020 与 RWG 两种版本分别通过原项目 15 种功能组合检查。
- 仿真执行原厂 LUT 复制和菜单确定代码；GUI 服务由模型提供，传感器／ISP／HEVC 硬件没有被仿真。
- 官方输入 SHA、模块 CRC、升级包 CRC／SHA1、输出回读和限定修改范围核验。
- 拒绝修改过的原厂输入、已占用的插入区、已有曲线改动，以及重新封装后带额外改动的有效 CRC 升级包。

当时尚待实机确认（04.18 已完成）：

- 真实 H.265 视频的黑位、中灰、灰阶单调性、RGB 通道和高光截止标定；多个 ISO／帧率下的复核。
- 实拍验证的 REDWideGamutRGB 支持；目前只是已接入矩阵的研究候选。
- 文件元数据的实拍复核：标签改写只经过 ARM 仿真，需用 ffprobe 与 ExifTool 检查新录制的片段。菜单摘要和帮助仍可能显示 N-Log。
- 设置持久化的实机复核：原厂写入非易失存储的路径未定位，QEMU 也不模拟断电后重新读回。开关是 0x12 组内的真实属性，与色调属性同一组、同一类型（kind 9，4 字节），但重启后能否保留要在相机上确认；失败时回到原生 N-Log，标签也同步回到 N-LOG。
- 历史文件的回放隔离：当前钩子依据当前 H.265 文件类型与 R2Y 色调选择，不依据历史文件身份；回放行为需要额外验证。
- 真机启动、菜单、录制稳定性、温度与长时间录制验证。离线检查不能证明机身安全。

修正版已在 QEMU 验证启动、新增菜单显示、选中、返回和重新进入后的标记。继续切换视频模式后，CAPTG 先在 0x41170D84 发生内存访问异常，诊断转储随后读取未建模硬件地址 0x15080014，仿真器停止；视频输出与录制没有通过验证。后续已完成原厂 3.11／实验版原生 N-Log／实验版 RWG 的六次对照：基础配置三组故障链完全一致；补齐 Movie 仿真输入后三组都进入视频取景，原故障不再出现，但切回拍照后三组均出现相同 Err。此次菜单测试不等于传感器／ISP 像素验证。

以上为开发阶段记录。

## 构建与复核

安装 requirements-log3g10-research.txt 中的依赖后，从工程根目录运行。四项基础功能默认读取仓库自带的 `resources/*.bin` 预编译补丁（与原项目 [v0.3.0-r1 toolkit ZIP](https://github.com/XinmiaoZhao/NikonFirmwarePatch/releases/tag/v0.3.0-r1) 中的文件相同，哈希由 `resources/compiled.json` 固定），或加 `--code-source source --compiler clang` 从源码编译。`--card-wav` 默认读取仓库自带的 `resources/cardwav.bin`，其中 10 个重放原厂指令的位置已清零，构建时从输入填回，不需要 LLVM。加 `--card-wav-source source` 则用 LLVM／clang 19.1.5（clang、ld.lld、llvm-nm、llvm-objcopy、llvm-objdump，目录由 `Z8_LLVM_BIN` 指定）编译，结果必须与 `resources/cardwav.json` 一致；源码模式会在构建目录写出新的 `cardwav.bin`／`cardwav.json`，维护者审核后替换。

~~~sh
python experimental_log3g10.py Z_8_0311.bin --output build/my-log3g10-experiment
python experimental_log3g10_verify.py Z_8_0311.bin build/my-log3g10-experiment/Z_8_0413.bin
python -m unittest discover -s tests -p test_log3g10.py -v
~~~

默认 BT.2020 输出身份为 04.13.e0。RWG 版本需要显式选择：

~~~sh
python experimental_log3g10.py Z_8_0311.bin --gamut rwg-research --version 04.14 --tag e1 --output build/my-rwg-experiment
python experimental_log3g10_verify.py Z_8_0311.bin build/my-rwg-experiment/Z_8_0414.bin --gamut rwg-research --version 04.14 --tag e1
~~~

每次使用新的输出目录。程序不自动复制到存储卡，不操作相机，也不发布文件。核验入口不信任输出 manifest，但字节重建复用了补丁实现；原生指令仿真和结构断言提供额外的语义检查。

## 资料与归属

- [RED Log3G10 与 RWG 白皮书](https://docs.red.com/955-0187/PDF/915-0187%20Rev-C%20%20%20RED%20OPS,%20White%20Paper%20on%20REDWideGamutRGB%20and%20Log3G10.pdf)：曲线公式、锚点和色域参考矩阵。
- [Nikon N-Log Specification](https://download.nikonimglib.com/archive3/hDCmK00m9JDI03RPruD74xpoU905/N-Log_Specification_(En)01.pdf)：N-Log 曲线、BT.2020 色域、D65。
- [Nikon Z8 Video File Types](https://onlinemanual.nikonimglib.com/z8/en/video_file_types_40.html)：H.265 10-bit 的色调和色域。
- [ShiSheng233/NLoader-apps Log3G10 研究](https://github.com/ShiSheng233/NLoader-apps/tree/0912deac4aff767af56f3ebf9b3f093faff35744/log3g10)：229 点网格、灰点、Z6III／ZR 处理表关系，以及 Z8 的表位于固件而非可写 RAM 的说明。这里只用其公开研究核对结构，未移植其相机应用代码。

新增源码沿用本项目 GPL-3.0-only；不改变 Nikon 固件或所引资料的许可。

## 无后缀 04.14 实机测试候选

内部身份均为 04.14 的版本，运行与尾部的八字节字段使用 04.14 加三个 NUL 填充，完整模块名为 eg2070_0414.bi。除身份和重新计算的校验信息外，功能字节与 04.14.e1 对照候选相同；无后缀不代表验证等级提高。

~~~sh
python experimental_log3g10.py Z_8_0311.bin --gamut rwg-research --version 04.14 --no-tag --output build/my-plain-0414
python experimental_log3g10_verify.py Z_8_0311.bin build/my-plain-0414/Z_8_0414.bin --gamut rwg-research --version 04.14 --no-tag
~~~

## 无后缀 04.15 实机测试候选

04.15 在 04.14 的基础上加入私有 NlgGamma 表与 Log3G10 文件标签，完整模块名为 eg2070_0415.bi。实拍已确认文件标签生效；同场景 N-Log 对照显示，中性区域的曲线与 Log3G10 表相差约 1 个码值，RWG 矩阵影响实际像素，结果倾向于矩阵在 log 前，但高光和高饱和颜色尚未覆盖。上文“缺少实拍证明”的条目以此处更新为准。

~~~sh
python experimental_log3g10.py Z_8_0311.bin --gamut rwg-research --version 04.15 --no-tag --output build/my-plain-0415
python experimental_log3g10_verify.py Z_8_0311.bin build/my-plain-0415/Z_8_0415.bin --gamut rwg-research --version 04.15 --no-tag
~~~

## 无后缀 04.17 S-Log3 候选

04.17 使用与 Log3G10 相同的三道条件和相同的钩子，只替换数据：私有 Lut1 与 NlgGamma 写入 Sony S-Log3，矩阵换成 BT.2020→S-Gamut3，菜单行、取景图块和 Picture Control 名分别为 S-Log3 / S-Gamut3、SLOG3、S-LOG3。这是单独的固件，菜单里没有 Log3G10 行。

数值来源：

| 项目 | 取值 | 来源 |
|---|---|---|
| 曲线常量 | 420、261.5、95、171.2102946929、0.01125、1023 | Sony 提供给 ACES 的 [IDT.Sony.SLog3_SGamut3.ctl](https://github.com/ampas/aces-dev/blob/710ecbe52c87ce9f4a1e02c8ddf7ea0d6b611cc8/transforms/ctl/idt/vendorSupplied/sony/IDT.Sony.SLog3_SGamut3.ctl) |
| S-Gamut3 基色 | R 0.730/0.280，G 0.140/0.855，B 0.100/−0.050，D65 | 取自 colour-science 收录的 Sony 数据；用这组基色经 CAT02 推出的 S-Gamut3→ACES 矩阵，与上述 Sony 文件里的矩阵相差约 5e-11 |
| BT.2020→S-Gamut3 | 由上述基色和 ITU-R BT.2020 基色推导 | Sony 没有发布这张矩阵 |

Sony 的 Technical Summary 原文件没有取到（试过的地址分别返回 403 和 404），所以没有逐字核对原文。

S-Log3 按 10-bit 码值定义，表值为码值 × 32：黑 95、18% 灰 420、90% 白 598。实拍片段的范围标记为 full，所以文件里的码值除以 1023 就是公式的输出。节点网格仍沿用“400 = 18% 灰”的假设，灰点落在 384 与 416 两个节点之间，插值后是 419.92。

~~~sh
python experimental_log3g10.py Z_8_0311.bin --gamut sgamut3-slog3 --version 04.17 --no-tag --card-wav --output build/my-0417
~~~

## 无后缀 04.18 双行候选

04.18 把 04.16 和 04.17 放进同一个固件：H.265 10-bit 的色调模式页多出两行，Log3G10 / RWG test 和 S-Log3 / S-Gamut3。开关属性 0x03001229 取 1 表示 Log3G10，取 2 表示 S-Log3，0 是原厂。两行都映射到原厂色调值 2（N-Log），不新增枚举。

每一行各有一份私有 Lut1、NlgGamma、色域矩阵和 Picture Control 定义。第一行的数据放在与 04.16 相同的地址，内容逐字节相同；第二行的数据放在这些地址往上 0x4000 处，内容与 04.17 相同。取景图块的图片编号从 0x1862 起依次是 L3G10 的填充和轮廓，接着是 SLOG3 的填充和轮廓。文件标签（VUI、colr 都是 2/2/1）对两行相同，只能靠取景图块或 Picture Control 名区分。

钩子按开关值选数据，其他值（包括 3 及以上）一律走原厂路径。ARM 仿真对开关值 0 到 3 逐一检查。

~~~sh
python experimental_log3g10.py Z_8_0311.bin --gamut rwg-slog3-dual --version 04.18 --no-tag --card-wav --output build/my-0418
~~~

维护者的 04.18 完整升级包 SHA256 为 `f790e606d828cabdc4d491ebe755427e25272e12e93dc405b29d076d7538a44e`；使用预编译单元或 LLVM 19.1.5 源码编译都得到此结果。

复核 04.18 输出：

~~~sh
python experimental_log3g10_verify.py Z_8_0311.bin build/my-0418/Z_8_0418.bin --gamut rwg-slog3-dual --version 04.18 --no-tag --card-wav
~~~

04.18 的实机检查项（维护者已完成）：

1. 在 Log3G10、S-Log3、N-Log 之间来回切换，特别是两个私有行之间直接切换；每次确认取景标签变化并各录几秒。
2. 用 ExifTool 确认 Picture Control 名分别是 LOG3G10 和 S-LOG3，VUI 和 colr 都是 2/2/1。
3. 同一场景、同样曝光录三段；S-Log3 的中性灰码值应比 Log3G10 高约 79（420 对 341）。
4. 分别选两行后关机再开机，确认选择保留。
5. 拍一段过曝内容，检查表顶端附近是否有断层。
