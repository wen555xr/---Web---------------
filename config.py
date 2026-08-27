"""全局配置。敏感信息优先从环境变量 / .env 读取，未配置时使用本地默认值。"""
import os  # 导入 os 模块，用于读取环境变量
from pathlib import Path  # 导入 Path，用于面向对象的路径处理

from dotenv import load_dotenv  # 导入 python-dotenv 的加载函数

load_dotenv()  # 读取 .env 文件内容并注入环境变量（真实环境变量优先级更高）

BASE_DIR = Path(__file__).resolve().parent  # 项目根目录：当前文件所在目录的绝对路径

# MySQL 连接串（SQLAlchemy URI）。默认连本机 root/123456，库名 netops。
SQLALCHEMY_DATABASE_URI = os.getenv(  # 从环境变量读取数据库连接串
    "DATABASE_URL",  # 环境变量名
    "mysql+pymysql://root:123456@127.0.0.1:3306/netops?charset=utf8mb4",  # 未配置时的默认值
)
SQLALCHEMY_TRACK_MODIFICATIONS = False  # 关闭对象变更信号跟踪，省内存、避免告警

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-me")  # Flask 会话签名密钥，优先读环境变量

# 模拟模式：True 时不连真实设备，用 MockSession 返回仿真华为 VRP 输出，方便本地演示。
MOCK_MODE = os.getenv("MOCK_MODE", "True").lower() in ("1", "true", "yes")  # 判断是否等于 1/true/yes，得到布尔值（默认 True）

# 配置备份输出目录
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", BASE_DIR / "backups"))  # 备份目录：优先环境变量，默认项目根目录下 backups/
