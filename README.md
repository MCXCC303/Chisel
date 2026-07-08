<div align="center">

```
 ██████╗██╗  ██╗██╗███████╗███████╗██╗
██╔════╝██║  ██║██║██╔════╝██╔════╝██║
██║     ███████║██║███████╗█████╗  ██║
██║     ██╔══██║██║╚════██║██╔══╝  ██║
╚██████╗██║  ██║██║███████║███████╗███████╗
 ╚═════╝╚═╝  ╚═╝╚═╝╚══════╝╚══════╝╚══════╝
```

**Claude Code 会话历史记录迁移工具**

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://python.org)
[![Textual](https://img.shields.io/badge/Textual-0.80+-0175C2)](https://github.com/Textualize/textual)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

</div>

---

Claude Code 的历史记录完整迁移工具。

## 快速开始

```bash
pip install -e .

# 交互模式（推荐）
chisel

# CLI 模式
chisel scan                                      # 查看所有项目
chisel pack -p '/path/to/project' -o out.tar.gz  # 导出
chisel info out.tar.gz                           # 查看包内容
chisel unpack out.tar.gz                         # 导入
```

## 迁移内容

一次打包会携带以下数据，从而确保迁移后在新机器上与原来完全一致：

| 数据类型 | 说明 |
|---------|------|
| **会话记录** | `.jsonl` 格式的完整对话历史，包含每轮问答、工具调用、文件操作 |
| **文件历史** | 会话中 Claude Code 修改过的文件快照，保留代码变更记录 |
| **任务状态** | 会话中的任务列表（Todo 列表）进度 |
| **项目元数据** | `claude.json` 中该项目的配置：最终会话 ID、累计费用、权限设置 |
| **命令行历史** | `history.jsonl` 中属于该项目的所有指令记录 |
| **全局配置** | `settings.json`、`stats-cache.json` |

## 扫描

```bash
chisel scan

# 输出示例
# /home/alice/projects/my-app
#   encoded: -home-alice-projects-my-app
#   sessions: 24
#   history: 18
```

指定非默认的数据目录：

```bash
chisel scan --claude-dir /path/to/backup/.claude --claude-json /path/to/backup/.claude.json
```

## 打包

将指定项目打包为 `.tar.gz` 迁移包：

```bash
# 打包单个项目
chisel pack -p '/home/alice/projects/my-app' -o my-app.tar.gz

# 打包多个项目
chisel pack -p '/path/project-a' -p '/path/project-b' -o multi.tar.gz

# 不指定 -p 则打包全部项目
chisel pack -o full-backup.tar.gz
```

## 查看包信息

```bash
chisel info my-app.tar.gz
```

输出包的元数据：创建时间、来源主机、项目数量、会话数量、占位符列表。

## 解包

将迁移包恢复到目标环境：

```bash
# 基础解包（自动将原用户名替换为当前用户名）
chisel unpack my-app.tar.gz

# 手动映射项目路径
chisel unpack my-app.tar.gz --map '__CM_PROJECT_0__=/home/bob/new-project'

# 指定目标目录
chisel unpack my-app.tar.gz --target-dir /custom/.claude --target-json /custom/.claude.json

# 模拟运行，查看将执行哪些操作
chisel unpack my-app.tar.gz --dry-run
```

### 智能合并

| 场景 | 处理方式 |
|------|---------|
| 包中的会话是目标的延续（目标行在包中都有，包有更多行） | **更新**为包中的版本 |
| 目标是包的延续（包的行目标中都有，目标有更多行） | **保留**目标版本 |
| 两边内容分叉（存在不一致的行） | **跳过**，保护已有数据 |

## 清理

删除已失效（项目目录不再存在或已改名）的冗余历史记录：

```bash
chisel clean --dry-run    # 预览将删除的内容
chisel clean              # 执行清理
```

> 建议先对需要清理的会话进行打包，然后再进行清理。

## 交互模式

```
chisel
```

交互模式下可以浏览项目列表、选择要打包的会话、预览对话内容、配置路径映射，所有操作均有界面引导，且具有完整的操作帮助。

## 安装

```bash
# 从源码安装
git clone https://github.com/MCXCC303/Chisel.git
cd Chisel
pip install -e .
```

依赖：Python >= 3.10、Textual >= 0.80、Rich >= 13.0。

## 许可

MIT License
