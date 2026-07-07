<div align="center">

```
 ██████╗  ██╗      ██╗██╗███████╗███████╗██╗               
██╔════╝██║      ██║██║██╔════╝██╔════╝██║               
██║               ███████║██║███████╗█████╗      ██║               
██║               ██╔══██║██║╚════██║██╔══╝      ██║               
╚██████╗██║      ██║██║███████║███████╗███████╗
   ╚═════╝╚═╝      ╚═╝╚═╝╚══════╝╚══════╝╚══════╝
```

<h1 aligh="center">Chisel - Claude Code 会话历史记录迁移工具</h1>

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://python.org)
[![Textual](https://img.shields.io/badge/Textual-0.80+-0175C2)](https://github.com/Textualize/textual)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

</div>

---

使用 Chisel 快速在不同机器之间迁移 Claude Code 对话记录。

## 快速开始

```bash
# 安装
pip install -e .

# 启动（交互模式）
python -m chisel

# CLI 模式
python -m chisel pack -p '/path/to/project' -o output.tar.gz
python -m chisel unpack output.tar.gz --map '__CM_PROJECT_0__=/new/path'
python -m chisel scan
python -m chisel info output.tar.gz
```

## 功能

| 功能 | 说明 |
|------|------|
| **打包** | 从 `~/.claude/` 提取项目历史，生成 `.tar.gz` 迁移包 |
| **解包** | 恢复迁移包到新环境，自动合并已有数据 |
| **预览** | 打包前查看会话内容，支持分批加载 |
| **路径映射** | 自动替换用户名，支持自定义目标路径 |

## 项目结构

```
chisel/
├── cli.py            # CLI 入口
├── models.py         # 数据模型
├── scanner.py        # 扫描器：发现项目和会话
├── packer.py         # 打包器：生成 .tar.gz 归档
├── unpacker.py       # 解包器：路径映射 + 合并
├── utils.py          # 路径编码等工具
├── help/             # 帮助文档（Markdown，按章节拆分）
│   ├── 01-overview.md
│   ├── 02-how-it-works.md
│   ├── 03-pack.md
│   ├── 04-unpack.md
│   ├── 05-preview.md
│   └── 06-shortcuts.md
└── tui/              # TUI 界面（Textual）
    ├── app.py        # ChiselApp + CSS 加载
    ├── start.py      # 启动页
    ├── pack.py       # 打包流程（扫描→配置→进度）
    ├── unpack.py     # 解包流程（选择→映射→进度）
    ├── preview.py    # 会话预览（分批加载 + 富文本渲染）
    ├── help.py       # 帮助页面（双栏 Markdown）
    ├── about.py      # 关于页面
    ├── message.py    # 消息弹窗
    ├── helpers.py    # 辅助函数
    └── css/          # 样式（按页面拆分）
        ├── base.css
        ├── start.css
        ├── pack.css
        ├── unpack.css
        ├── preview.css
        ├── help.css
        ├── about.css
        └── message.css
```

## 依赖

- Python >= 3.10
- [Textual](https://github.com/Textualize/textual) — TUI 框架
- [Rich](https://github.com/Textualize/rich) — 终端富文本

## 工作原理

### 打包

1. 扫描 `~/.claude/projects/` 发现所有项目
2. 提取会话 `.jsonl`、文件历史、任务数据、`history.jsonl` 条目
3. 项目绝对路径替换为占位符（`__CM_PROJECT_N__`）
4. 打包为 `.tar.gz` 归档

### 解包

1. 读取迁移包元数据，获取占位符列表
2. 用户指定每个项目在新环境的目标路径（默认替换用户名）
3. 写入会话文件、合并 `claude.json`、追加 `history.jsonl`
4. 已有数据不会被覆盖，按 UUID 去重

## 许可

MIT License
