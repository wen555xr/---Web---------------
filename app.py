"""Flask 应用入口：页面路由 + 设备 CRUD + 任务 API + 后台线程。"""
import threading  # 导入 threading，用于启动后台任务线程

from flask import Flask, jsonify, redirect, render_template, request, url_for  # 导入 Flask 及常用辅助函数

import netmiko_utils  # 导入封装好的网络任务逻辑（三个任务函数）
from config import (BACKUP_DIR, MOCK_MODE, SECRET_KEY,  # 导入备份目录、模拟模式开关、密钥
                    SQLALCHEMY_DATABASE_URI, SQLALCHEMY_TRACK_MODIFICATIONS)  # 导入数据库连接串与跟踪开关
from models import db, Device, TaskLog  # 导入数据库实例与两个模型类

app = Flask(__name__)  # 创建 Flask 应用实例
app.config["SQLALCHEMY_DATABASE_URI"] = SQLALCHEMY_DATABASE_URI  # 配置数据库连接串
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = SQLALCHEMY_TRACK_MODIFICATIONS  # 关闭变更跟踪
app.config["SECRET_KEY"] = SECRET_KEY  # 配置会话签名密钥
db.init_app(app)  # 将数据库实例绑定到应用

TASK_LABELS = {  # 任务类型英文 key → 中文显示名映射表
    "backup": "备份配置",
    "create_vlans": "创建 VLAN",
    "port_security_scan": "端口安全扫描",
}
STATUS_LABELS = {  # 任务状态英文 → 中文显示名映射表
    "running": "执行中",
    "success": "成功",
    "partial": "部分成功",
    "failed": "失败",
}


@app.context_processor  # 注册上下文处理器，返回值会注入所有模板
def inject_globals():  # 定义上下文注入函数
    return {"MOCK_MODE": MOCK_MODE}  # 把 MOCK_MODE 提供给所有模板使用


@app.template_filter("task_label")  # 注册名为 task_label 的模板过滤器
def task_label(name):  # 定义过滤器函数
    return TASK_LABELS.get(name, name)  # 把英文任务名转中文，找不到则原样返回


@app.template_filter("status_label")  # 注册名为 status_label 的模板过滤器
def status_label(name):  # 定义过滤器函数
    return STATUS_LABELS.get(name, name)  # 把英文状态转中文，找不到则原样返回


# ---- 页面路由 ----
@app.route("/")  # 首页路由（GET /）
def index():  # 首页视图函数
    devices = Device.query.filter_by(enabled=True).order_by(Device.name).all()  # 查询所有启用设备并按名称排序
    return render_template("index.html", devices=devices)  # 渲染首页模板并传入设备列表


@app.route("/devices")  # 设备管理页路由（GET /devices）
def devices_page():  # 设备管理页视图函数
    devices = Device.query.order_by(Device.name).all()  # 查询全部设备并按名称排序
    return render_template("devices.html", devices=devices)  # 渲染设备管理页模板


@app.route("/tasks")  # 任务历史页路由（GET /tasks）
def tasks_page():  # 任务历史页视图函数
    tasks = TaskLog.query.order_by(TaskLog.created_at.desc()).limit(50).all()  # 按创建时间倒序取最近 50 条任务
    return render_template("tasks.html", tasks=tasks)  # 渲染任务历史页模板


# ---- 设备 CRUD ----
@app.route("/devices", methods=["POST"])  # 新增设备路由（POST /devices）
def device_create():  # 新增设备视图函数
    d = Device(  # 构造一个 Device 对象
        name=request.form["name"].strip(),  # 设备名：取表单值并去除首尾空白
        ip_address=request.form["ip_address"].strip(),  # 管理 IP：去空白
        username=request.form.get("username", "").strip() or "admin",  # 用户名：为空则默认 admin
        password=request.form.get("password", "") or "Admin@123",  # 密码：为空则默认 Admin@123
        device_type=request.form.get("device_type", "").strip() or "huawei_vrp",  # 类型：为空则默认 huawei_vrp
        enabled=request.form.get("enabled") == "on",  # 是否启用：勾选了才为 True
    )
    db.session.add(d)  # 将新设备加入会话
    db.session.commit()  # 提交事务写入数据库
    return redirect(url_for("devices_page"))  # 重定向回设备管理页


@app.route("/devices/<int:device_id>/update", methods=["POST"])  # 更新设备路由（POST）
def device_update(device_id):  # 更新设备视图函数，接收路径参数 device_id
    d = db.session.get(Device, device_id)  # 根据 ID 查询设备
    if not d:  # 设备不存在
        return redirect(url_for("devices_page"))  # 直接重定向回列表页
    d.name = request.form["name"].strip()  # 更新设备名
    d.ip_address = request.form["ip_address"].strip()  # 更新管理 IP
    d.username = request.form.get("username", "").strip() or "admin"  # 更新用户名
    new_password = request.form.get("password", "")  # 读取新密码字段
    if new_password:  # 仅当填写了新密码才更新
        d.password = new_password  # 更新密码
    d.device_type = request.form.get("device_type", "").strip() or "huawei_vrp"  # 更新设备类型
    d.enabled = request.form.get("enabled") == "on"  # 更新启用状态
    db.session.commit()  # 提交更新
    return redirect(url_for("devices_page"))  # 重定向回列表页


@app.route("/devices/<int:device_id>/delete", methods=["POST"])  # 删除设备路由（POST）
def device_delete(device_id):  # 删除设备视图函数
    d = db.session.get(Device, device_id)  # 根据 ID 查询设备
    if d:  # 设备存在才执行删除
        db.session.delete(d)  # 标记删除
        db.session.commit()  # 提交删除
    return redirect(url_for("devices_page"))  # 重定向回列表页


# ---- 任务 API ----
def _start_task(task_name, func, *args):  # 创建任务记录并启动后台线程执行任务
    """创建 TaskLog 记录并启动后台线程执行任务，返回 task_id。"""
    task = TaskLog(task_name=task_name, status="running")  # 新建一条“执行中”的任务记录
    db.session.add(task)  # 加入会话
    db.session.commit()  # 立即提交，以便前端能拿到 task_id 进行轮询
    task_id = task.id  # 取出自增主键 ID

    def wrapper():  # 定义后台线程要执行的包装函数
        with app.app_context():  # 后台线程需手动进入应用上下文才能使用 db 与查询
            func(task_id, *args)  # 调用真正的任务函数并传入 task_id 等参数

    threading.Thread(target=wrapper, daemon=True).start()  # 启动守护线程执行 wrapper（主进程退出时随之结束）
    return task_id  # 立即返回 task_id 给前端


@app.route("/api/tasks/backup", methods=["POST"])  # 备份任务 API
def api_backup():  # 备份任务视图函数
    task_id = _start_task("backup", netmiko_utils.run_backup)  # 启动备份任务
    return jsonify({"task_id": task_id})  # 返回 JSON，包含 task_id


@app.route("/api/tasks/vlans", methods=["POST"])  # 创建 VLAN 任务 API
def api_vlans():  # 创建 VLAN 视图函数
    data = request.get_json(silent=True) or request.form  # 优先解析 JSON，失败则回退表单数据
    device_id = int(data.get("device_id"))  # 目标设备 ID，转整数
    vlan_start = int(data.get("vlan_start", 100))  # 起始 VLAN，默认 100
    vlan_end = int(data.get("vlan_end", 149))  # 结束 VLAN，默认 149
    task_id = _start_task("create_vlans", netmiko_utils.run_create_vlans,  # 启动建 VLAN 任务
                          device_id, vlan_start, vlan_end)  # 传入设备 ID 与 VLAN 范围
    return jsonify({"task_id": task_id})  # 返回 task_id


@app.route("/api/tasks/port-security", methods=["POST"])  # 端口安全扫描任务 API
def api_port_security():  # 端口安全扫描视图函数
    task_id = _start_task("port_security_scan", netmiko_utils.run_port_security_scan)  # 启动扫描任务
    return jsonify({"task_id": task_id})  # 返回 task_id


@app.route("/api/tasks/<int:task_id>")  # 任务状态查询 API（GET）
def api_task_status(task_id):  # 任务状态视图函数
    task = db.session.get(TaskLog, task_id)  # 根据 ID 查询任务
    if not task:  # 任务不存在
        return jsonify({"error": "not found"}), 404  # 返回 404 错误
    return jsonify({  # 返回任务状态 JSON
        "task_id": task.id,  # 任务 ID
        "task_name": task.task_name,  # 任务类型
        "status": task.status,  # 状态
        "summary": task.summary,  # 摘要
        "result_detail": task.result_detail,  # 完整输出
    })


if __name__ == "__main__":  # 仅当直接运行 python app.py 时执行
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)  # 启动时确保备份目录存在
    app.run(debug=True, host="127.0.0.1", port=5000)  # 以调试模式在 127.0.0.1:5000 启动
