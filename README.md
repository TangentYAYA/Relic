# Relic

Relic — Digital Forensics & Evidence Integrity Platform 是一个面向课程设计的
数字取证分析平台原型，重点是可复现的证据完整性、审计追溯和核心取证工作流。
它不声称完全替代 Autopsy。

## 当前能力

- 案件创建、打开、关闭、元数据和案件目录隔离。
- RAW/dd 镜像登记、TSK 分区/文件系统识别和流式 SHA-256。
- `fls` 文件树、`istat` 元数据、`icat` 导出及导出哈希。
- PNG/JPEG/GIF/PDF/ZIP/文本识别、扩展名异常、纯文本搜索、EXIF、标记和备注。
- 后台分析任务、UTC 时间线、JSONL 审计哈希链和检查点。
- 质量检查和只生成 Markdown 的取证报告。

## 环境和启动

目标环境为 Windows 10/11、Python 3.11、PySide6 和官方 TSK CLI。

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:RELIC_TSK_BIN = "D:\sleuthkit\sleuthkit\bin"
$env:RELIC_CASE_ROOT = "D:\RelicData"
.\.venv\Scripts\python.exe main.py
```

`RELIC_TSK_BIN` 和 `RELIC_CASE_ROOT` 都可以换成实际路径。原始镜像只保存绝对路径；
派生数据写入案件目录，不写入镜像目录。

## 测试和打包

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --name Relic main.py
```

实际测试结果见 [docs/test_results.md](docs/test_results.md) 和
[docs/performance_results.md](docs/performance_results.md)。

## 安全边界

软件以只读方式读取原始镜像，并使用参数列表调用 TSK，不通过 shell 拼接输入。
这不是硬件写保护；拥有文件系统权限的人仍可能重写整个审计日志，因此应使用外部
权限控制、只读介质或独立可信存储保护证据和日志。
