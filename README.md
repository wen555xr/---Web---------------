# 基于 Web 的轻量级网络自动化运维小工具

一个用 Flask + Netmiko + MySQL 实现的轻量级网络自动化运维工具，前端页面提供三个一键操作：

- 💾 **一键备份所有交换机配置** — 备份所有启用设备的 running-config 到 `backups/` 目录
- 🔀 **批量创建 VLAN** — 对选中设备下发 `vlan batch <start> to <end>`
- 🛡️ **端口安全策略扫描** — 扫描所有设备接口的端口安全启用情况

默认面向 **华为 VRP** 设备（Netmiko `device_type = huawei_vrp`），并内置**模拟模式**，
不连真实设备也能完整演示。

## 解决了什么问题

网络运维里几类重复、易错、难留痕的手工工作，都能用这个工具一键完成。核心思路是：
**把「逐台 SSH 登录敲命令」变成「网页上点一下」，把「散落在脑子和 Excel 里的信息」变成「有台账、有日志」**。

| 运维痛点 | 传统做法 | 本工具的做法 |
|---|---|---|
| **配置备份靠手工** | 逐台 SSH 登录，敲 `display current-configuration` 后复制粘贴；设备一多就耗时、容易漏、文件名也乱 | 一键备份所有启用设备的 running-config，按「设备名 + 时间戳」落盘到 `backups/` |
| **批量变更重复劳动** | 在多台交换机上建 VLAN 要逐台逐条敲命令，重复且容易敲错参数 | 选中设备，一键批量下发 `vlan batch <start> to <end>`，并自动 `save` |
| **安全合规检查靠人盯** | 端口安全是否启用，靠人工逐台逐接口核对，慢且难以汇总成表 | 一键扫描所有接口的端口安全启用状态，自动汇总出「设备 + 接口 + 是否启用」清单 |
| **设备与任务无台账** | 设备信息散落在 Excel 或人脑里，操作无记录、事后难追溯 | 用 MySQL 管理设备清单 + 任务日志，每次操作留痕、可回看结果与失败原因 |
| **怕直接改生产出错** | 直接对生产设备下发命令风险高，验证流程成本大 | 内置模拟模式，不连真实设备也能完整跑通流程，确认无误后再切生产 |

> 一句话：**面向小规模网络、无专职自动化平台时的轻量替代方案**——不引入 Ansible/TTP 等重平台，
> 一个 Python 脚本 + 网页就能把最常做的备份、变更、巡检三件事自动化并留痕。

| 层 | 选型 |
|---|---|
| 后端 | Flask + Flask-SQLAlchemy |
| 网络连接 | Netmiko（`huawei_vrp`） |
| 数据库 | MySQL（驱动 PyMySQL） |
| 前端 | Jinja2 模板 + 原生 HTML/CSS/JS（无构建步骤） |
| 任务并发 | `threading` 后台线程 + 前端轮询 |

## 目录结构

```
netops-tool/
├── app.py              # Flask 入口 + 页面路由 + 设备 CRUD + 任务 API
├── config.py           # DB URI、SECRET_KEY、MOCK_MODE、BACKUP_DIR
├── models.py           # Device、TaskLog 模型
├── netmiko_utils.py    # 连接封装 + 三个任务 + MockSession
├── init_db.py          # 建表 + 预置示例设备
├── requirements.txt
├── templates/          # base / index / devices / tasks
├── static/             # style.css / app.js
└── backups/            # 配置备份输出目录（运行时自动创建）
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 创建数据库

```sql
CREATE DATABASE netops CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
```

### 3. 配置数据库连接

复制 `.env` 或直接改 `config.py`。默认连接串：

```
mysql+pymysql://root:root@127.0.0.1:3306/netops?charset=utf8mb4
```

如账号密码不同，在项目根目录创建 `.env`：

```
DATABASE_URL=mysql+pymysql://你的用户:你的密码@127.0.0.1:3306/netops?charset=utf8mb4
```

### 4. 初始化数据库（建表 + 预置 2 台示例设备）

```bash
python init_db.py
```

### 5. 启动

```bash
python app.py
```

打开 http://127.0.0.1:5000 ，默认 **MOCK_MODE=True（模拟模式）**，直接点三个按钮即可演示。

## 联真实设备

1. 在「设备管理」页录入真实设备的 IP / 用户名 / 密码（厂商选「华为 VRP」）。
2. 关闭模拟模式，在 `.env` 中设置：

```
MOCK_MODE=False
```

3. 重启后点击任务按钮，将通过 SSH 真实下发命令。

> 真实设备的命令会**真实执行**，尤其 `vlan batch` / `save` 会修改设备配置。
> 请务必先在模拟模式验证流程，再连接生产设备。

## ⚠️ 注意事项

- **密码明文存储**：设备密码在 MVP 阶段明文存于 MySQL，仅限内网使用；生产环境建议用
  `cryptography` 的 Fernet 加密后再入库。
- **无登录鉴权**：本工具未做用户认证，请勿直接暴露到公网。
- **save 确认提示**：华为 VRP 的 `save` 会交互确认，`netmiko_utils._save_config()` 用
  `expect_string` 处理；不同版本提示符略有差异，若保存失败会在结果中提示需人工确认。

## 说明

- 模拟模式不依赖真实网络环境，也**不强依赖 Netmiko 库**（仅在非模拟模式下按需导入），
  适合用于开发调试与功能演示。
