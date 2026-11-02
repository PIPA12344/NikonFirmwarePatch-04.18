# 卡内 WAV 快门声 / Card WAV shutter sound

[简体中文](#简体中文) · [English](#english)

## 简体中文

**状态：维护者已在 Z8 实机上完成验证。** 另有离线 ARM 集成场景和 WAV 导入边界测试。这仍是非官方实验固件，风险说明见文末。

这是 [s3lemming/z9-firmware-patch](https://github.com/s3lemming/z9-firmware-patch/tree/88a6f3e5195d7f38792dc8eddeb1526fde4096dc) 卡内 WAV 快门声的 Z8 C3.11 移植（`z8cardwav/`，GPL-3.0-or-later）。它从存储卡读取你自己的 WAV 作为快门声，**不占用、不修改**原厂 A–E 声音。原作者未审阅或背书此移植。

### 构建

在构建命令中加 `--card-wav`。它目前只能与 H.265 Log3G10 / S-Log3 实验一起构建（`experimental_log3g10.py`），`patch.py` 不提供此选项：

```sh
python experimental_log3g10.py "/path/to/Z_8_0311.bin" --gamut rwg-slog3-dual --version 04.18 --no-tag --card-wav --output build/my-0418
```

默认使用仓库自带的 `resources/cardwav.bin`，不需要编译器。该文件中 10 处重放原厂指令的位置已清零，构建时从你的 3.11 读出填回。加 `--card-wav-source source` 可改用 LLVM／clang 19.1.5 从 `z8cardwav/firmware/` 源码编译，结果必须与 `resources/cardwav.json` 的固定哈希一致。

### 准备 WAV

| 要求 | 取值 |
|---|---|
| 格式 | RIFF WAV，未压缩 PCM，16 位小端 |
| 采样率／声道 | 48 kHz，双声道（立体声） |
| 长度 | 大于 0，最长 1.5 秒（288,000 字节 PCM） |
| 文件名 | 可打印 ASCII，扩展名 `.wav`（大小写均可），含扩展名最多 111 个字符 |
| 位置 | 存储卡根目录下的 `CUSTOM_SOUND` 文件夹 |

相机不会转换 MP3、其他采样率或单声道。可以先用 FFmpeg 转换格式（不会剪辑，超过 1.5 秒请先自行剪短）：

```sh
ffmpeg -i input.wav -ar 48000 -ac 2 -c:a pcm_s16le CUSTOM_SOUND/my_shutter.wav
```

### 在相机上使用

1. 把 WAV 放进卡上的 `CUSTOM_SOUND` 文件夹，插入相机。
2. 设定菜单 → 照相机声音 → 快门音类型。原厂 A–E 之后多出一行 **Load WAV from card**（所有语言都显示英文）。
3. 进入后列出文件夹中的 WAV，最多显示 20 个；选择一个即可。
4. 选用自定义声音时，外层“类型”显示 **CUS**。想恢复原厂声音，重新选 A–E 即可。

选择结果保存在 `CUSTOM_SOUND/M2SND0.CFG` 与 `M2SND1.CFG`（两份交替写入），请不要删除。修改同名 WAV 后，重新选择一次即会重新读取并校验内容。

### 播放行为与限制

- 单拍（S／CL／CH）：每次拍摄从头播放，下一张会打断上一张，最后一张播放完整。
- C15：每张最多播放开头 50 ms；其他 Cxx：最多 40 ms。原生连拍停止后，剩余部分播放一次。不会为每张连拍排队播放完整声音。
- 每次开机最多缓存 20 种不同的声音内容。缓存满后仍可选用已缓存的声音，新内容需要重启后才能载入。

### 菜单行显示的错误信息

| 显示 | 含义 |
|---|---|
| Load failed - check WAV | 文件格式、长度或文件名不符合上表要求，或读取失败 |
| Save failed - check card | 选择结果无法写入卡（卡写保护、已满或未插卡） |
| Cache full - restart | 本次开机已缓存 20 种声音，重启后再选新的 |
| Audio busy - retry | 音频正在使用，稍后再试 |

### 验证

- 实机：维护者已在 Z8 上完成验证。
- WAV 导入器：格式错误、超长、截断、读取失败、提前结束、1.5 秒边界等组件场景。
- ARM 集成：在 Unicorn 中执行实际挂钩、适配后的 C 代码和部分原厂函数（`z8cardwav/verify_integration.py`）。底层卡、音频任务、绘制和设置存储使用测试桩。
- 完整固件封包、CRC／SHA1、模块边界与未改动区域回读。

这是非官方实验固件，可能造成数据丢失或相机故障，请勿用于不可替代的拍摄。

## English

**Status: camera-verified on a Z8 by the maintainer.** Offline ARM integration scenarios and WAV-import boundary tests also pass. It is still unofficial experimental firmware.

A Z8 C3.11 port (`z8cardwav/`, GPL-3.0-or-later) of the card WAV shutter sound from [s3lemming/z9-firmware-patch](https://github.com/s3lemming/z9-firmware-patch/tree/88a6f3e5195d7f38792dc8eddeb1526fde4096dc). It plays your own WAV from the card and leaves the stock A–E sounds untouched. The original author has not reviewed or endorsed this port.

**Build:** add `--card-wav` to `experimental_log3g10.py` (not available in `patch.py`). The bundled `resources/cardwav.bin` is used by default and needs no compiler; `--card-wav-source source` compiles with LLVM/clang 19.1.5 and must match `resources/cardwav.json`.

**WAV:** RIFF, uncompressed 16-bit little-endian PCM, 48 kHz stereo, longer than 0 and at most 1.5 s, printable-ASCII name ending in `.wav` (at most 111 characters), placed in `CUSTOM_SOUND` at the card root. No conversion happens in the camera.

**Camera:** Setup menu → Camera sounds → Type now ends with **Load WAV from card**; it lists up to 20 WAV files. A custom selection shows **CUS**; choose A–E to go back. The choice is stored in `CUSTOM_SOUND/M2SND0.CFG` and `M2SND1.CFG`; do not delete them.

**Playback:** single frame restarts each shot and the last one plays fully. C15 plays at most the first 50 ms per frame, other Cxx at most 40 ms; the remainder plays once after the burst stops. Up to 20 distinct sounds are cached per power-on.

**Menu messages:** `Load failed - check WAV`, `Save failed - check card`, `Cache full - restart`, `Audio busy - retry`.

Unofficial experimental firmware: it can cause data loss or camera malfunction. Do not use it for irreplaceable work.
