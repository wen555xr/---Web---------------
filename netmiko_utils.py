"""网络设备连接封装 + 三个运维任务的执行逻辑。

- connect_device()：根据 config.MOCK_MODE 返回真实 Netmiko 连接或 MockSession。
- run_backup / run_create_vlans / run_port_security_scan：在后台线程中执行，更新 TaskLog。

真实设备的连接库 Netmiko 只在非模拟模式下按需导入，模拟模式不依赖它也能跑通。
"""
import re
import time
from datetime import datetime

from config import BACKUP_DIR, MOCK_MODE
from models import db, Device, TaskLog

# 厂商 device_type 别名，统一映射到 Netmiko 支持的取值（预留多厂商扩展）
DEVICE_TYPE_ALIASES = {
    "huawei": "huawei_vrp",
    "huawei_vrp": "huawei_vrp",
    "cisco_ios": "cisco_ios",
}

# ---- 模拟模式用的仿真华为 VRP 输出样本 ----
MOCK_RUNNING_CONFIG = """#
sysname {name}
#
vlan batch 10 20 30
#
interface GigabitEthernet0/0/1
 port link-type access
 port default vlan 10
#
interface GigabitEthernet0/0/2
 port link-type access
 port default vlan 20
#
interface GigabitEthernet0/0/3
 port link-type trunk
 port trunk allow-pass vlan 10 20 30
#
return
"""

MOCK_PORT_SECURITY = """Port Security Configuration:
Interface                 Security     Max MAC   Current MAC
GigabitEthernet0/0/1      Enable       5          0
GigabitEthernet0/0/2      Enable       10         1
GigabitEthernet0/0/3      Disable      -          -
GigabitEthernet0/0/4      Disable      -          -
"""


class MockSession:
    """模拟会话：不连真实设备，按命令返回仿真的华为 VRP 输出，并模拟少量延迟。"""

    def __init__(self, device):
        self.device = device
        self.connected = False

    def __enter__(self):
        time.sleep(0.2)
        self.connected = True
        return self

    def __exit__(self, *exc):
        self.disconnect()

    def send_command(self, command):
        time.sleep(0.2)
        cmd = command.strip()
        if "current-configuration" in cmd or "saved-configuration" in cmd:
            return MOCK_RUNNING_CONFIG.format(name=self.device.name)
        if "port-security" in cmd:
            return MOCK_PORT_SECURITY
        return f"<{self.device.name}> {cmd}\n(mock: 命令已执行)"

    def send_config_set(self, commands):
        time.sleep(0.2)
        out = []
        for c in commands:
            out.append(f"[mock] {self.device.name}# {c}")
        return "\n".join(out)

    def disconnect(self):
        self.connected = False


def connect_device(device):
    """返回设备会话（真实或模拟），两者都可用 with 语法作为上下文管理器。"""
    if MOCK_MODE:
        return MockSession(device)

    from netmiko import ConnectHandler

    params = {
        "device_type": DEVICE_TYPE_ALIASES.get(device.device_type, "huawei_vrp"),
        "host": device.ip_address,
        "username": device.username,
        "password": device.password,
    }
    return ConnectHandler(**params)


def _save_config(conn):
    """华为 VRP 的 save 需要确认提示，用 expect_string 处理；模拟模式直接跳过。"""
    if MOCK_MODE:
        return "(模拟模式) 跳过 save"
    try:
        conn.send_command("save", expect_string=r"[Y/N]", read_timeout=15)
        conn.send_command("Y", expect_string=r"[<>\]\]", read_timeout=15)
        return "已执行 save"
    except Exception as e:
        return f"save 未完成（可能需人工确认）：{e}"


def _finish(task, status, summary, detail):
    task.status = status
    task.summary = summary
    task.result_detail = detail
    task.finished_at = datetime.now()
    db.session.commit()


def _get_task(task_id):
    return db.session.get(TaskLog, task_id)


# ---- 任务 1：一键备份所有交换机配置 ----
def run_backup(task_id):
    task = _get_task(task_id)
    devices = Device.query.filter_by(enabled=True).all()
    if not devices:
        _finish(task, "failed", "没有启用的设备", "请先在「设备管理」中添加并启用设备。")
        return

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    lines, success, failed = [], 0, 0

    for d in devices:
        try:
            with connect_device(d) as conn:
                config = conn.send_command("display current-configuration")
            filename = f"{d.name}_{timestamp}.cfg"
            (BACKUP_DIR / filename).write_text(config, encoding="utf-8")
            lines.append(f"[成功] {d.name} ({d.ip_address}) -> {filename}")
            success += 1
        except Exception as e:
            lines.append(f"[失败] {d.name} ({d.ip_address}) -> {e}")
            failed += 1

    status = "success" if failed == 0 else ("partial" if success else "failed")
    _finish(task, status, f"备份完成：成功 {success} 台，失败 {failed} 台", "\n".join(lines))


# ---- 任务 2：批量创建 VLAN ----
def run_create_vlans(task_id, device_id, vlan_start, vlan_end):
    task = _get_task(task_id)
    device = db.session.get(Device, device_id)
    if not device:
        _finish(task, "failed", "设备不存在", f"设备 ID {device_id} 不存在。")
        return
    if not (1 <= vlan_start <= vlan_end <= 4094):
        _finish(task, "failed", "VLAN 范围非法",
                f"范围应为 1~4094 且 start <= end，收到 {vlan_start}~{vlan_end}")
        return

    try:
        with connect_device(device) as conn:
            output = conn.send_config_set([f"vlan batch {vlan_start} to {vlan_end}"])
            save_out = _save_config(conn)
        count = vlan_end - vlan_start + 1
        detail = (f"下发命令：\n  vlan batch {vlan_start} to {vlan_end}\n\n"
                  f"设备输出：\n{output}\n\n{save_out}")
        _finish(task, "success",
                f"已在 {device.name} 上批量创建 VLAN {vlan_start}~{vlan_end}（共 {count} 个）", detail)
    except Exception as e:
        _finish(task, "failed", f"VLAN 创建失败：{e}", str(e))


# ---- 任务 3：端口安全策略扫描 ----
def parse_port_security(output):
    """从 display port-security 输出中解析接口与端口安全启用状态。"""
    rows = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        if re.match(r"^(GigabitEthernet|Ethernet|Eth-Trunk|GE|XGE|10GE|25GE|Vlanif)", line):
            enabled = "enable" in line.lower() and "disable" not in line.lower()
            rows.append({"interface": line.split()[0], "enabled": enabled, "raw": line})
    return rows


def run_port_security_scan(task_id):
    task = _get_task(task_id)
    devices = Device.query.filter_by(enabled=True).all()
    if not devices:
        _finish(task, "failed", "没有启用的设备", "请先添加并启用设备。")
        return

    lines, success, failed = [], 0, 0
    total_ifaces, total_enabled = 0, 0

    for d in devices:
        try:
            with connect_device(d) as conn:
                output = conn.send_command("display port-security")
            rows = parse_port_security(output)
            total_ifaces += len(rows)
            enabled_rows = [r for r in rows if r["enabled"]]
            total_enabled += len(enabled_rows)
            lines.append(f"【{d.name}】{d.ip_address}")
            for r in rows:
                lines.append(f"  - {r['interface']}: {'启用' if r['enabled'] else '未启用'}")
            success += 1
        except Exception as e:
            lines.append(f"[失败] {d.name} ({d.ip_address}) -> {e}")
            failed += 1

    status = "success" if failed == 0 else ("partial" if success else "failed")
    _finish(task, status,
            f"扫描完成：{success} 台设备，共 {total_ifaces} 个接口，其中启用端口安全 {total_enabled} 个",
            "\n".join(lines))
