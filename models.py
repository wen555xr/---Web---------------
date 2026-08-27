"""SQLAlchemy 数据模型：网络设备清单 + 任务执行记录。"""
from datetime import datetime  # 导入 datetime，用于生成默认时间戳

from flask_sqlalchemy import SQLAlchemy  # 导入 Flask-SQLAlchemy 的 ORM 核心类

db = SQLAlchemy()  # 创建全局 db 实例（暂不绑定 app，稍后在 app.py 里 init_app）


class Device(db.Model):  # 网络设备表模型，继承 SQLAlchemy 的 Model 基类
    __tablename__ = "devices"  # 指定对应的 MySQL 表名

    id = db.Column(db.Integer, primary_key=True)  # 主键：自增整数 ID
    name = db.Column(db.String(64), nullable=False, comment="设备名")  # 设备名：最长 64，非空
    ip_address = db.Column(db.String(64), nullable=False, unique=True, comment="管理 IP")  # 管理 IP：非空且唯一
    username = db.Column(db.String(64), nullable=False, default="admin")  # 登录用户名：默认 admin
    password = db.Column(db.String(128), nullable=False, default="Admin@123")  # 登录密码：默认 Admin@123
    device_type = db.Column(db.String(32), nullable=False, default="huawei_vrp")  # 厂商类型：默认华为 VRP
    enabled = db.Column(db.Boolean, nullable=False, default=True, comment="是否纳入批量操作")  # 是否启用（参与批量任务）
    created_at = db.Column(db.DateTime, default=datetime.now)  # 创建时间：插入时自动填当前时间
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)  # 更新时间：每次更新自动刷新


class TaskLog(db.Model):  # 任务执行记录表模型
    __tablename__ = "task_logs"  # 对应的 MySQL 表名

    id = db.Column(db.Integer, primary_key=True)  # 主键：自增整数 ID
    task_name = db.Column(db.String(64), nullable=False, comment="backup/create_vlans/port_security_scan")  # 任务类型标识
    status = db.Column(db.String(16), nullable=False, default="running")  # 状态：running/success/partial/failed
    summary = db.Column(db.Text, comment="简短摘要")  # 一句话结果摘要
    result_detail = db.Column(db.Text, comment="完整输出")  # 完整输出明细（多行文本）
    created_at = db.Column(db.DateTime, default=datetime.now)  # 创建时间
    finished_at = db.Column(db.DateTime)  # 完成时间：执行中为 NULL
