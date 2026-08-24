"""SQLAlchemy 数据模型：网络设备清单 + 任务执行记录。"""
from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Device(db.Model):
    __tablename__ = "devices"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False, comment="设备名")
    ip_address = db.Column(db.String(64), nullable=False, unique=True, comment="管理 IP")
    username = db.Column(db.String(64), nullable=False, default="admin")
    password = db.Column(db.String(128), nullable=False, default="Admin@123")
    device_type = db.Column(db.String(32), nullable=False, default="huawei_vrp")
    enabled = db.Column(db.Boolean, nullable=False, default=True, comment="是否纳入批量操作")
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)


class TaskLog(db.Model):
    __tablename__ = "task_logs"

    id = db.Column(db.Integer, primary_key=True)
    task_name = db.Column(db.String(64), nullable=False, comment="backup/create_vlans/port_security_scan")
    status = db.Column(db.String(16), nullable=False, default="running")
    summary = db.Column(db.Text, comment="简短摘要")
    result_detail = db.Column(db.Text, comment="完整输出")
    created_at = db.Column(db.DateTime, default=datetime.now)
    finished_at = db.Column(db.DateTime)
