# 发布包与独立验证

当前工具修订为 **v0.3.0-r1**，上一工具包为 **v0.3.0**。`-r1` 表示第一次主机工具修订，固件功能版本仍为 0.3.0。工具包版本与用户选择的固件版本独立。功能变化见[更新日志](../CHANGELOG.md)；公开附件以对应 Release 的源码提交和校验清单为准。

完整 toolkit ZIP 带全部源码、许可证、公开文档、固定配方及四份自编译补丁：`precapture.bin`、`pixelshift.bin`、`pixelshift-af.bin`、`opengate.bin`，位于 resources。**不分发原厂或修改后的完整固件、实拍原片、运行库、编译器。** 自动 Source code 归档和 Git 克隆不带二进制，需显式源码模式或同一版本完整 toolkit。默认预编译模式不调用 Clang，也不静默下载或编译。ProRes 指令由 Python 生成并匹配固定配方。

## 构建和核验

输入必须为官方 C3.11，99,051,117 B，SHA-256 `d67413c2ede6b9ce8887175f20700bd9fbad2a973a4820968c45503d15d80d96`。

`resources/compiled.json` 绑定四份代码的长度、哈希、符号地址、编译参数、编译器和源文件哈希；`resources/combinations.json` 为 15 种组合的修改窗口目录。旧 profile/precapture JSON 保留为历史参考，不是当前构建配方。`tools/review_recipes.py` 是维护者的显式配方导出器；不能以重新生成配方替代对改动的独立审核。

`verify.py` 不导入构建器、打包器或编码实现，也不拿输出自己的 manifest 作正确答案。它独立解封装、检查原始输入、全部声明窗口和未改字节、其他模块、版本指令／字符串／目录名以及 CRC／摘要。传入 `--features --version --tag` 才能核对用户原本要求的选项；省略时只检测实际功能和身份一致性。版本不要求递增：Z8 支持降级及同版本重刷，不同组合应使用不同身份。

manifest 记录源文件哈希和来源：toolkit 构建绑定 `release-manifest.json` 及源提交；Git checkout 在 git 可用时记录提交与是否干净。完整固件哈希只识别该次具体组合与身份，不代替字节审核，也不扩大实机范围。

## 发布者复现

先提交源码，再在干净的同一提交上生成。v0.3.0-r1 的生成与核验命令：

```sh
python -B tests/test_compiled_paths.py
python tools/build_release.py --tag v0.3.0-r1 --compiler clang --output /path/to/new-assets
python tools/check_release.py /path/to/new-assets/NikonFirmwarePatch-v0.3.0-r1-toolkit.zip --commit COMMIT_SHA
python tests/validate_distribution.py --archive /path/to/new-assets/NikonFirmwarePatch-v0.3.0-r1-toolkit.zip --archive-only --report /path/to/archive-report.json
python tests/validate_distribution.py --stock /path/to/Z_8_0311.bin --report /path/to/loader-report.json
python tests/validate_combinations.py --stock /path/to/Z_8_0311.bin --report /path/to/combinations-report.json
python tests/validate_prebuilt_cli.py --stock /path/to/Z_8_0311.bin --report /path/to/prebuilt-cli-report.json
python tools/check_repository.py --all
```

发布构建器只读取明确允许的已提交源码，自编译四份代码并逐项匹配记录；不读取完整固件。ZIP 使用固定时间和文件模式，含所有成员哈希与源提交。独立检查器核对精确成员清单、普通文件类型、总大小、源文件字节、代码长度及哈希和编译来源。多出固件、重复成员、缺失／损坏文件、错误提交均拒绝。

`SHA256SUMS.txt` 是 ZIP 校验清单。macOS 用 `shasum -a 256 -c SHA256SUMS.txt`，Linux 用 `sha256sum -c SHA256SUMS.txt`；Windows 可用 `Get-FileHash`。清单应从可信发布来源取得。固件实现变化先完成相应组合实机验收；仅主机路径修订保留同字节实现的既有实机记录，新增主机构建验证。由维护者推送和发布，上传后下载读回。版本附件保持不可变，修正另建版本。机器码和 ZIP 保持 Git 忽略，不能强制纳入。

当前功能与限制见[已知问题](known-issues.md)，验证结果见[当前版本验证](validation.md)，v0.2.0 历史验证见 [记录](validation-v0.2.0.md)。

发布前从最终审阅的干净提交生成工具包与校验清单，不混用不同提交的源码、文档和附件。修订版不改写 v0.3.0 或更早版本的 tag 与附件。贡献者与基础代码来源见 [NOTICE](../NOTICE.md#contributor-acknowledgements)。

## Windows 发布门

[Host checks](https://github.com/XinmiaoZhao/NikonFirmwarePatch/actions/workflows/host-checks.yml) 在 Windows Python 3.12／3.13、Linux 和 macOS 上运行路径回归。发布前以 `firmware_smoke=true` 手动运行 Windows 构建：取得哈希固定的公开 v0.3.0 工具包，仅取与修订版相同的四份机器码，配合当前发布源码，从 Nikon 取得精确哈希的 C 3.11，运行 issue #12 的组合和全选组合，并独立核验生成固件。工作流保持只读权限，保存源码、机器码与输出哈希；发布者再与最终工具包逐项比对。输入与输出只在 runner 临时目录使用，只上传 JSON 结果。执行记录与结果链接随 Release 提供。
