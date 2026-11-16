# Relic 模块设计

## 模块职责

| 层 | 模块 | 职责 |
|---|---|---|
| UI | `ui.pages` | Dashboard、案件、证据、文件系统、内容、时间线、任务、审计、报告、设置页面 |
| UI | `ui.models` | 使用 Qt Model/View 映射文件清单和任务状态 |
| 应用 | `services.case` | 新建、打开、关闭案件和案件隔离 |
| 应用 | `services.evidence` | 注册镜像、只读校验、分区与文件系统探测 |
| 应用 | `services.hash` | 4 MiB 流式 SHA-256、基准和结束复核 |
| 应用 | `services.file` | 清单、类型、注释和导出编排 |
| 应用 | `services.analysis` | 任务注册、状态、取消、结果持久化 |
| 应用 | `services.search` | 纯文本关键词搜索和结果定位 |
| 应用 | `services.timeline` | MAC 时间和 `fls -m` 结果统一 |
| 应用 | `services.audit` | 操作审计和错误记录 |
| 应用 | `services.integrity` | 哈希、审计链和质量检查 |
| 应用 | `services.report` | 从真实持久化数据生成 Markdown |
| 基础设施 | `infrastructure.tsk_adapter` | 参数白名单、subprocess、stdout/stderr、超时 |
| 基础设施 | `infrastructure.repositories` | JSON 原子更新、JSONL 增量读取/追加 |
| 基础设施 | `infrastructure.hash_engine` | 文件流哈希 |
| 基础设施 | `infrastructure.extractors` | 文件签名、文本、EXIF；未知格式明确返回 unknown |
| 基础设施 | `infrastructure.audit_writer` | 序列化写入 SHA-256 哈希链 |
| 基础设施 | `infrastructure.report_generator` | Markdown 模板和真实数据校验 |

## 当前已实现模块

- `domain.models`：`Case`、`Evidence`、`Partition` 和 `FileSystemInfo` 数据模型。
- `services.case_service.CaseService`：案件新建、列表、打开、关闭、元数据更新和目录隔离。
- `services.evidence_service.EvidenceService`：RAW 路径注册、mmls 分区识别、fsstat 文件系统识别、基线哈希和审计。
- `infrastructure.repositories`：JSON 原子替换写入和 JSONL 追加写入。
- `infrastructure.hash_engine`：固定 4 MiB 分块的流式 SHA-256。
- `infrastructure.tsk_adapter.TSKAdapter`：仅通过参数列表调用 TSK CLI，并检查路径、超时和返回码。
- `services.file_service.FileService`：使用 `fls -m` 流式生成 `FileEntry`，增量写入 `files.jsonl`，调用 `istat` 查看元数据，并使用 `icat` 导出到案件 `exports`。
- `services.analysis_service.AnalysisService`：独立执行签名类型识别、扩展名异常检测、纯文本关键词搜索、Pillow EXIF、案件缩略图和文件标记；统一返回 `AnalysisResult`。
- `services.task_engine.AnalysisTaskEngine`：注册独立 handler，在线程池中执行任务，管理 pending/running/completed/failed/cancelled、进度、错误、取消和历史 JSONL。
- `services.timeline_service.TimelineService`：合并文件系统时间与软件审计时间，统一转换为 UTC，提供时间范围和事件类型筛选。
- `services.integrity_service.IntegrityService`：证据结束哈希复核、审计链/检查点验证、完整性摘要和自动化质量检查。
- `services.report_service.ReportService`：只读取案件持久化数据生成 Markdown，支持报告源码读取和 UI 预览；生成动作写入审计链。
- `ui.pages`：案件和证据页面通过服务接口交互；哈希使用 `QThreadPool` 后台执行。

当前证据加载只保存原始镜像的绝对路径和元数据，派生 JSON 与审计文件写入案件目录；软件级只读不等同于硬件写保护。

文件浏览的机器解析格式是 TSK `fls -m` 的 11 列 mactime 记录：
`MD5|path|inode|mode|uid|gid|size|atime|mtime|ctime|crtime`。
`istat` 仍保留 TSK 原始文本，以避免丢失文件系统特有字段；`icat` 输出直接流入
案件 exports 目录，再计算导出文件 SHA-256。TSK 命令仍只存在于 `TSKAdapter`。

基础分析模块不以扩展名作为真实类型依据：先读取内容签名，再对 UTF-8 无 NUL
文本做有限文本识别。扩展名异常只产生 warning，不推断恶意行为。Pillow 是唯一新增
图像依赖，负责 EXIF 和案件目录内缩略图；原始证据路径不作为输出目录。

任务引擎只负责调度和状态，不包含文件类型、搜索或 EXIF 逻辑；具体功能以 handler
注册。时间线中的 `source_kind=filesystem` 表示证据内文件时间，
`source_kind=software_audit` 表示 Relic 操作时间，界面固定标明 UTC。

审计链验证逐行检查 JSON、必需字段、固定字段顺序规范化哈希、sequence 连续性、
previous_hash、记录顺序和记录内容。检查点只记录验证时的最后序号和哈希；
其安全性取决于案件数据目录的外部权限控制，不能被描述为防篡改存储。

报告服务不从 UI 状态或演示数据取值。缺失文件、哈希、任务、分析或审计信息会以
“未完成”“未提供”或 warning 出现在报告中，不会被转换为成功结论。报告输出固定为
案件 `reports` 目录下的 `.md` 文件，不生成 HTML。

## TSKAdapter 接口草案

```python
class TSKAdapter(Protocol):
    def version(self) -> TSKVersion: ...
    def inspect_partitions(self, image: ReadOnlyImage) -> list[Partition]: ...
    def inspect_filesystem(
        self, image: ReadOnlyImage, offset_sectors: int
    ) -> FileSystemInfo: ...
    def list_files(
        self, image: ReadOnlyImage, offset_sectors: int, recursive: bool
    ) -> Iterable[FileEntry]: ...
    def stat(
        self, image: ReadOnlyImage, offset_sectors: int, inode: int
    ) -> FileMetadata: ...
    def extract(
        self, image: ReadOnlyImage, offset_sectors: int, inode: int,
        destination: BinaryIO
    ) -> ExtractionStats: ...
```

实现约束：

- `image` 只能是已注册且存在的普通文件；不能是案件目录内的可写副本。
- 偏移只能是非负整数 sectors，不能由 UI 拼接成字符串。
- 每次调用保存命令、参数摘要、版本、返回码、stdout 和 stderr 的摘要。
- `icat` 输出写入案件目录中的目标流；不把整个文件读入内存。
- 超时、非零返回码、解析失败和取消都必须成为显式错误。

## 偏移传递规则

1. `mmls` 的分区起始值记录为 `Partition.start_sector`。
2. 对 RAW 镜像，文件系统调用的 `-o` 等于选定分区的 `start_sector`，单位是 512-byte device sectors，除非实际 `mmls` 输出/镜像元数据证明设备扇区不同。
3. `mmls -b` 仅在明确知道设备扇区大小时使用；不能把文件系统 block size 当作 `-b`。
4. `fsstat`、`fls`、`istat`、`icat` 必须接收同一个 `filesystem_offset_sectors`。
5. 不把字节偏移直接传给 `-o`；UI 可显示 `sector * sector_size`，内部仍保存 sectors。
6. 无分区表且文件系统直接位于镜像起点时，使用 offset 0，并记录 `partition_scheme=none`。
7. 解析异常或多个候选分区时暂停自动分析并要求用户选择，不能猜测。

## 后台任务机制

`AnalysisTask` 由应用层创建，`QRunnable` 在 `QThreadPool` 执行。worker 通过信号报告 `progress`, `message`, `result`, `error`, `finished`；取消使用线程安全 `CancellationToken`，在哈希块、TSK 子进程轮询和文件遍历之间检查。Qt 主线程只更新模型和状态。

## 异常与日志

错误类型至少包括 `ConfigurationError`、`EvidenceAccessError`、`TSKProcessError`、`TSKParseError`、`TaskCancelledError`、`RepositoryError` 和 `IntegrityError`。用户可见消息应脱敏；详细命令、返回码、stderr 摘要和 traceback 进入应用日志。关键成功、失败、取消和完整性结论进入不可删除的审计 JSONL。
