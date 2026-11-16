# Relic 环境验证报告

## 结论

本报告记录 2026-11-16 在 Windows 工作站上的实际验证结果。项目虚拟环境已经具备 Python 和测试基础设施；官方 TSK CLI 通过绝对路径验证成功，但当前 PowerShell 进程的 `PATH` 尚未刷新，因此实现阶段应支持显式配置 CLI 目录，不应只依赖 `PATH`。

## 环境结果

| 项目 | 实际结果 | 结论 |
|---|---|---|
| 操作系统 | Windows 11 家庭中文版，10.0.26200，Build 26200 | 满足 Windows 10/11 目标 |
| Python | `.venv\Scripts\python.exe`，Python 3.11.9 | 满足固定版本 |
| pip | pip 24.0，Python 3.11 环境 | 可用 |
| PySide6 | 6.12.0 | 已安装 |
| pytest | 9.2.0 | 已安装 |
| PyInstaller | 6.22.3 | 已安装并完成打包烟测 |
| pytsk3 | 20260715，TSK lib 4.15.0 | Python 绑定已安装，不替代 CLI |
| TSK CLI | `D:\sleuthkit\sleuthkit\bin` | 五个目标程序均存在 |
| CLI 版本 | The Sleuth Kit ver 4.14.0 | 已通过 `-V` 实际验证 |

## CLI 路径

已验证的文件：

```text
D:\sleuthkit\sleuthkit\bin\mmls.exe
D:\sleuthkit\sleuthkit\bin\fsstat.exe
D:\sleuthkit\sleuthkit\bin\fls.exe
D:\sleuthkit\sleuthkit\bin\istat.exe
D:\sleuthkit\sleuthkit\bin\icat.exe
```

配置项应优先保存该目录，调用时通过 `Path(cli_dir) / executable` 形成参数列表。启动检查可以接受 PATH，但必须把最终解析出的绝对路径和版本写入环境诊断及审计日志。

## 实际命令验证

对每个程序执行 `<tool>.exe -V`：

- 返回码为 0。
- 标准输出为 `The Sleuth Kit ver 4.14.0`。

对每个程序执行 `-h`：

- 五个程序均输出 usage 和参数说明。
- 因为这些版本没有统一的 `-h` 选项，返回码为 1，输出分别为 `Unknown argument`、`Invalid argument` 或缺少必要参数。
- 这不是安装失败；适配器不能把“有 usage 输出的帮助请求”当作正常分析失败。

关键帮助输出确认：

```text
mmls: -o imgoffset      volume-system start offset, in sectors
fsstat: -o imgoffset    file-system start offset, in sectors
fls: -o imgoffset      file-system offset, in sectors
istat: -o imgoffset    file-system offset, in sectors
icat: -o imgoffset     file-system offset, in sectors
fls: -m dir/           mactime input format
```

## 受控输入验证

创建并随后删除了一个 1 MiB 全零临时文件，仅用于错误路径验证，未放入镜像目录：

- `mmls` 返回码 1，未识别有效分区表。
- `fsstat` 返回码 1，输出 `Cannot determine file system type`。
- `fls` 返回码 1，输出 `Cannot determine file system type`。

没有真实 RAW 镜像，因此本阶段没有声称验证某一种分区表或文件系统的正常输出。阶段二应使用经授权的测试镜像验证真实分区和文件清单解析。

## 风险与决策

1. `pytsk3` 报告的库版本 4.15.0 与 CLI 4.14.0 不一致。首版以 CLI 作为 subprocess 后端，启动时记录两者版本；若需要混用，必须建立兼容性测试。
2. TSK 输出主要是面向人的文本。`fls -m` 可用于时间线，但常规 `mmls`、`fsstat`、`istat` 输出应由版本固定的解析器处理，并保留原始 stdout/stderr。
3. 不接受 shell 字符串拼接。所有调用使用参数列表、超时、返回码检查和单独的 stdout/stderr。
4. CLI 路径未刷新到当前进程 PATH。配置文件中的绝对目录是首版可靠方案。
