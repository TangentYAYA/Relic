# Relic 最终测试结果

测试日期：2026-11-16。测试均在 Windows 11 Build 26200、Python 3.11.9、
PySide6 6.12.0、pytest 9.2.0、Pillow 12.3.0、TSK CLI 4.14.0 上执行。

## 功能回归

命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

实际结果：**25 passed in 3.00s**。

现有测试覆盖案件和隔离、RAW 加载、mmls 分区、fsstat 失败处理、SHA-256、
fls/istat/icat、导出哈希、文件类型、扩展名异常、关键词、EXIF、标记、
任务生命周期/取消、时间线、审计链、检查点、质量检查和 Markdown 报告。

## 异常验证

| 场景 | 实际结果 |
|---|---|
| 镜像路径不存在 | `FileNotFoundError` |
| 镜像路径是目录 | `FileNotFoundError` |
| TSK 目录不存在 | `TSKError: TSK executable not found` |
| TSK 命令超时 | `TSKProcessError: mmls timed out` |
| TSK 返回错误 | `TSKProcessError: fsstat failed (1): Cannot determine file system type` |
| 文件无法提取 | 既有测试确认 `icat failed`，且失败临时导出被删除 |
| JSON 损坏 | `JSONDecodeError` |
| JSONL 记录损坏 | 报告生成返回 `JSONDecodeError`，没有生成成功报告 |
| 审计内容/顺序/序号篡改 | 既有副本篡改测试验证链失败 |
| 审计尾部变化 | 检查点验证失败 |
| 任务取消 | 既有测试验证 `cancelled` 状态 |
| 报告生成失败 | 损坏 JSONL 显式失败 |
| 磁盘空间不足 | 未强行消耗磁盘模拟；未声称通过。底层写入错误会向调用方传播。 |

## 提供的检材

`D:\Autopsy\Autopsy分析资料` 包含 `001Win10.E01` 至 `E15` 和 `.info`，
总大小实测 16,065,175,949 bytes。`.info` 明确说明这是 Guymager EWF 分卷。
当前 Relic 只实现 RAW/dd，不实现 EWF 解码；直接把首分片交给 `mmls` 虽返回
分区表，但不能代表完整 EWF 检材已正确加载，因此本结果不计入成功功能验收。

## 安全检查

- 原始镜像读取路径经过 `Path.is_file()` 校验，哈希使用 `rb` 流式读取。
- TSK 使用参数列表、独立 stdout/stderr 和超时；代码中没有 `shell=True`。
- 原始镜像目录不创建临时文件；案件 JSON/JSONL、导出和报告位于案件目录。
- 审计记录追加写入；链使用 genesis、连续序号、前置哈希和规范化记录哈希。
- 篡改验证只修改测试副本，不修改真实案件日志。
- PySide6 offscreen 导航烟测通过；后台哈希期间事件循环实测保持响应。

## 打包

PyInstaller 6.22.3 实测成功生成：

`D:\Relic\dist\Relic\Relic.exe`

打包程序启动烟测保持进程运行 5 秒后由测试进程结束，说明首次启动和依赖收集
成功。TSK 不打包进 EXE，运行时仍需通过 `RELIC_TSK_BIN` 配置外部 CLI。
