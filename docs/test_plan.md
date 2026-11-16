# Relic 测试与验收计划

## 当前环境基线

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pytest --version
& 'D:\sleuthkit\sleuthkit\bin\mmls.exe' -V
```

实现后所有测试在 `.venv` 中运行，避免使用系统 Python 3.14。

## 分阶段验收

| 阶段 | 验收标准 | 测试证据 |
|---|---|---|
| 环境与适配器 | 五个 CLI 路径、版本、返回码、stderr 可记录；超时和缺失可诊断 | CLI smoke tests |
| 案件 | 新建/打开/关闭；案件目录隔离；字段持久化 | service tests |
| 证据 | RAW 注册、存在性、大小、只读策略、基线/结束 SHA-256 | hash fixtures |
| 分区与文件系统 | offset 单位明确；分区到 fs offset 一致；异常不猜测 | controlled images |
| 文件清单 | JSONL 一行一条、增量写入、重启可恢复、大文件不进内存 | JSONL tests |
| 文件分析 | 已支持签名、未知类型、扩展名异常、文本、EXIF 边界行为可验证 | fixture corpus |
| 任务引擎 | queued/running/succeeded/failed/cancelled、进度、错误和取消 | worker tests |
| 审计完整性 | sequence 连续、previous_hash 正确、checkpoint 可检查尾截断 | tamper tests |
| 质量检查 | 未完成数据不能 pass；结束复核 mismatch 可见 | quality tests |
| 报告 | 只生成 Markdown；所有结果可追溯；无结果不伪造 | report tests |
| UI | 长任务不阻塞；Model/View 处理大清单；错误可见 | Qt smoke tests |
| 文件浏览与导出 | `fls -m` 文件记录、JSONL、istat、icat 内容和哈希闭环 | `test_file_browser_export.py` |
| 基础文件分析 | 签名、异常扩展名、纯文本搜索、EXIF、空 EXIF、标记、缩略图和错误 | `test_analysis_service.py` |
| 统一任务与时间线 | 状态生命周期、失败、取消、多任务、UTC 时间线和筛选 | `test_task_engine_timeline.py` |
| 审计与完整性 | genesis、链验证、内容/顺序篡改、检查点、结束复核、质量检查 | `test_integrity.py`, `test_case_evidence.py` |
| Markdown 报告 | 真实案件字段、证据哈希、分析摘要、时间线、导出哈希、审计、质量检查和 Markdown 预览 | `test_report_service.py` |

## TSK 适配器测试

测试数据必须是授权的最小 RAW 镜像，至少覆盖：

1. 无分区表、文件系统位于 sector 0。
2. 有分区表、文件系统从非零 sector 开始。
3. 未识别镜像和截断镜像。
4. 文件系统内目录、普通文件、删除项和 inode。

每个命令测试断言：

- 参数列表中没有 shell 拼接。
- `-o` 是整数 sector 偏移。
- 进程返回码、stdout、stderr 和版本被保存。
- 非零返回码映射为明确的 `TSKProcessError`。
- 解析失败映射为 `TSKParseError`，不产生成功形状的空结果。

## 安全和性能测试

- 证据父目录中不存在临时文件。
- 证据文件不能被应用写入；案件目录可写且与证据目录隔离。
- 4 MiB 分块哈希与标准工具结果一致。
- 大文件测试的内存增长不随文件大小线性增加。
- JSONL 单 writer 并发测试不出现交错行。
- 审计记录篡改、删除、尾部截断都能被检查点或链校验报告。
- 子进程超时和取消后被可靠终止，GUI 线程保持响应。

## 测试命令

阶段二开始后，最小验证命令为：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit -q
.\.venv\Scripts\python.exe -m pytest tests\integration\test_tsk_adapter.py -q
```

阶段三当前实现验证：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_case_evidence.py -q
```

当前结果：6 passed。覆盖案件重新打开、多案件隔离、RAW 加载、真实
`mmls` 分区识别、无效文件系统的显式 `fsstat` 错误、SHA-256 正确性、
基线持久化和审计记录。GUI 后台哈希使用 `QThreadPool`，另以 offscreen
Qt smoke test 验证主窗口和页面导航仍可构建。

当前文件浏览与导出验证：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_file_browser_export.py -q
```

使用已知 FAT 镜像验证 `fls` 根目录、inode 3、文件大小、`istat` 输出、
目录 inode 浏览、`icat` 导出内容、导出 SHA-256、案件 `exports.jsonl` 和错误 inode。

当前基础文件分析验证：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_analysis_service.py -q
```

使用 Pillow 生成的 PNG/JPEG 与签名样本验证类型识别、JPEG 伪装为 TXT、
关键词命中和二进制跳过、真实 EXIF 字段、空 EXIF、案件缩略图、标记持久化
以及缺失文件错误。

当前任务引擎与时间线验证：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_task_engine_timeline.py -q
```

覆盖任务注册、启动、进度、完成、失败、取消、多个任务并行，以及文件系统
时间与软件审计时间的 UTC 排序和事件类型筛选。

当前审计与完整性验证：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_integrity.py -q
```

篡改测试只复制 JSONL 审计文件后修改副本，不修改真实案件审计记录；
覆盖首条 genesis、哈希重算、序号/前置哈希、检查点尾部变化和质量检查。

当前报告验证：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_report_service.py -q
```

使用测试案件逐项核对案件信息、取证人员、环境、证据、基准/结束哈希、
分区、文件系统、类型统计、扩展名异常、关键词、EXIF、时间线、标记、
导出哈希、审计链、检查点、质量检查和完整性结论。测试确认输出为 `.md`
且不包含 HTML。
