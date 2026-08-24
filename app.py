"""Flask 应用入口：页面路由 + 设备 CRUD + 任务 API + 后台线程。"""
import threading

from flask import Flask, jsonify, redirect, render_template, request, url_for

import netmiko_utils
from config import (BACKUP_DIR, MOCK_MODE, SECRET_KEY,
                    SQLALCHEMY_DATABASE_URI, SQLALCHEMY_TRACK_MODIFICATIONS)
from models import db, Device, TaskLog

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = SQLALCHEMY_DATABASE_URI
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = SQLALCHEMY_TRACK_MODIFICATIONS
app.config["SECRET_KEY"] = SECRET_KEY
db.init_app(app)

TASK_LABELS = {
    "backup": "备份配置",
    "create_vlans": "创建 VLAN",
    "port_security_scan": "端口安全扫描",
}
STATUS_LABELS = {
    "running": "执行中",
    "success": "成功",
    "partial": "部分成功",
    "failed": "失败",
}


@app.context_processor
def inject_globals():
    return {"MOCK_MODE": MOCK_MODE}


@app.template_filter("task_label")
def task_label(name):
    return TASK_LABELS.get(name, name)


@app.template_filter("status_label")
def status_label(name):
    return STATUS_LABELS.get(name, name)


# ---- 页面路由 ----
@app.route("/")
def index():
    devices = Device.query.filter_by(enabled=True).order_by(Device.name).all()
    return render_template("index.html", devices=devices)


@app.route("/devices")
def devices_page():
    devices = Device.query.order_by(Device.name).all()
    return render_template("devices.html", devices=devices)


@app.route("/tasks")
def tasks_page():
    tasks = TaskLog.query.order_by(TaskLog.created_at.desc()).limit(50).all()
    return render_template("tasks.html", tasks=tasks)


# ---- 设备 CRUD ----
@app.route("/devices", methods=["POST"])
def device_create():
    d = Device(
        name=request.form["name"].strip(),
        ip_address=request.form["ip_address"].strip(),
        username=request.form.get("username", "").strip() or "admin",
        password=request.form.get("password", "") or "Admin@123",
        device_type=request.form.get("device_type", "").strip() or "huawei_vrp",
        enabled=request.form.get("enabled") == "on",
    )
    db.session.add(d)
    db.session.commit()
    return redirect(url_for("devices_page"))


@app.route("/devices/<int:device_id>/update", methods=["POST"])
def device_update(device_id):
    d = db.session.get(Device, device_id)
    if not d:
        return redirect(url_for("devices_page"))
    d.name = request.form["name"].strip()
    d.ip_address = request.form["ip_address"].strip()
    d.username = request.form.get("username", "").strip() or "admin"
    new_password = request.form.get("password", "")
    if new_password:
        d.password = new_password
    d.device_type = request.form.get("device_type", "").strip() or "huawei_vrp"
    d.enabled = request.form.get("enabled") == "on"
    db.session.commit()
    return redirect(url_for("devices_page"))


@app.route("/devices/<int:device_id>/delete", methods=["POST"])
def device_delete(device_id):
    d = db.session.get(Device, device_id)
    if d:
        db.session.delete(d)
        db.session.commit()
    return redirect(url_for("devices_page"))


# ---- 任务 API ----
def _start_task(task_name, func, *args):
    """创建 TaskLog 记录并启动后台线程执行任务，返回 task_id。"""
    task = TaskLog(task_name=task_name, status="running")
    db.session.add(task)
    db.session.commit()
    task_id = task.id

    def wrapper():
        with app.app_context():
            func(task_id, *args)

    threading.Thread(target=wrapper, daemon=True).start()
    return task_id


@app.route("/api/tasks/backup", methods=["POST"])
def api_backup():
    task_id = _start_task("backup", netmiko_utils.run_backup)
    return jsonify({"task_id": task_id})


@app.route("/api/tasks/vlans", methods=["POST"])
def api_vlans():
    data = request.get_json(silent=True) or request.form
    device_id = int(data.get("device_id"))
    vlan_start = int(data.get("vlan_start", 100))
    vlan_end = int(data.get("vlan_end", 149))
    task_id = _start_task("create_vlans", netmiko_utils.run_create_vlans,
                          device_id, vlan_start, vlan_end)
    return jsonify({"task_id": task_id})


@app.route("/api/tasks/port-security", methods=["POST"])
def api_port_security():
    task_id = _start_task("port_security_scan", netmiko_utils.run_port_security_scan)
    return jsonify({"task_id": task_id})


@app.route("/api/tasks/<int:task_id>")
def api_task_status(task_id):
    task = db.session.get(TaskLog, task_id)
    if not task:
        return jsonify({"error": "not found"}), 404
    return jsonify({
        "task_id": task.id,
        "task_name": task.task_name,
        "status": task.status,
        "summary": task.summary,
        "result_detail": task.result_detail,
    })


if __name__ == "__main__":
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    app.run(debug=True, host="127.0.0.1", port=5000)
