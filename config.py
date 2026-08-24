"""全局配置。敏感信息优先从环境变量 / .env 读取，未配置时使用本地默认值。"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

# MySQL 连接串（SQLAlchemy URI）。默认连本机 root/root，库名 netops。
SQLALCHEMY_DATABASE_URI = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://root:123456@127.0.0.1:3306/netops?charset=utf8mb4",
)
SQLALCHEMY_TRACK_MODIFICATIONS = False

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-me")

# 模拟模式：True 时不连真实设备，用 MockSession 返回仿真华为 VRP 输出，方便本地演示。
MOCK_MODE = os.getenv("MOCK_MODE", "True").lower() in ("1", "true", "yes")

# 配置备份输出目录
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", BASE_DIR / "backups"))
