"""网络设备连接封装 + 三个运维任务的执行逻辑。

- connect_device()：根据 config.MOCK_MODE 返回真实 Netmiko 连接或 MockSession。
- run_backup / run_create_vlans / run_port_security_scan：在后台线程中执行，更新 TaskLog。

真实设备的连接库 Netmiko 只在非模拟模式下按需导入，模拟模式不依赖它也能跑通。
"""
import re  # 导入正则模块，用于解析端口安全输出
import time  # 导入 time 模块，用于模拟连接/执行延迟
from datetime import datetime  # 导入 datetime，用于生成时间戳与完成时间

from config import BACKUP_DIR, MOCK_MODE  # 导入备份目录与模拟模式开关
from models import db, Device, TaskLog  # 导入数据库实例与两个模型

# 厂商 device_type 别名，统一映射到 Netmiko 支持的取值（预留多厂商扩展）
DEVICE_TYPE_ALIASES = {  # 别名映射表
    "huawei": "huawei_vrp",  # 用户写 huawei 时映射成 Netmiko 认识的 huawei_vrp
    "huawei_vrp": "huawei_vrp",  # 已是标准名，保持不变
    "cisco_ios": "cisco_ios",  # 思科类型
}

# ---- 模拟模式用的仿真华为 VRP 输出样本 ----
# 仿真 running-config 文本；其中的 {name} 占位符会被 .format(name=...) 替换成设备名
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

# 仿真端口安全输出表（固定文本，供解析函数测试）
MOCK_PORT_SECURITY = """Port Security Configuration:
Interface                 Security     Max MAC   Current MAC
GigabitEthernet0/0/1      Enable       5          0
GigabitEthernet0/0/2      Enable       10         1
GigabitEthernet0/0/3      Disable      -          -
GigabitEthernet0/0/4      Disable      -          -
"""


class MockSession:  # 模拟会话类：不连真实设备，返回仿真华为 VRP 输出
    """模拟会话：不连真实设备，按命令返回仿真的华为 VRP 输出，并模拟少量延迟。"""

    def __init__(self, device):  # 构造方法，接收设备对象
        self.device = device  # 保存设备对象，供返回文本使用设备名
        self.connected = False  # 初始标记为未连接

    def __enter__(self):  # with 语句进入时调用
        time.sleep(0.2)  # 模拟连接耗时 0.2 秒
        self.connected = True  # 标记已连接
        return self  # 返回 self，供 with ... as 绑定

    def __exit__(self, *exc):  # with 语句退出时调用
        self.disconnect()  # 断开连接

    def send_command(self, command):  # 模拟下发单条命令
        time.sleep(0.2)  # 模拟命令执行延迟
        cmd = command.strip()  # 去掉命令首尾空白
        if "current-configuration" in cmd or "saved-configuration" in cmd:  # 请求配置类命令
            return MOCK_RUNNING_CONFIG.format(name=self.device.name)  # 返回仿真配置并替换设备名
        if "port-security" in cmd:  # 请求端口安全命令
            return MOCK_PORT_SECURITY  # 返回仿真端口安全表
        return f"<{self.device.name}> {cmd}\n(mock: 命令已执行)"  # 其它命令返回提示符回显

    def send_config_set(self, commands):  # 模拟批量下发配置命令
        time.sleep(0.2)  # 模拟延迟
        out = []  # 用于累积每行输出
        for c in commands:  # 遍历每条配置命令
            out.append(f"[mock] {self.device.name}# {c}")  # 模拟配置模式提示符回显
        return "\n".join(out)  # 多行拼成一个字符串返回

    def disconnect(self):  # 断开连接
        self.connected = False  # 标记为未连接


def connect_device(device):  # 返回设备会话（真实或模拟）
    """返回设备会话（真实或模拟），两者都可用 with 语法作为上下文管理器。"""
    if MOCK_MODE:  # 模拟模式
        return MockSession(device)  # 返回模拟会话，不连真实设备

    from netmiko import ConnectHandler  # 仅真实模式才按需导入 Netmiko

    params = {  # 组装 Netmiko 连接参数
        "device_type": DEVICE_TYPE_ALIASES.get(device.device_type, "huawei_vrp"),  # 用别名表映射厂商类型
        "host": device.ip_address,  # 目标 IP
        "username": device.username,  # 用户名
        "password": device.password,  # 密码
    }
    return ConnectHandler(**params)  # 建立真实 SSH 连接并返回连接对象


def _save_config(conn):  # 保存配置：华为 VRP 的 save 需要交互确认
    """华为 VRP 的 save 需要确认提示，用 expect_string 处理；模拟模式直接跳过。"""
    if MOCK_MODE:  # 模拟模式
        return "(模拟模式) 跳过 save"  # 不真正保存，返回说明

    try:  # 尝试保存，捕获确认提示差异等异常
        conn.send_command("save", expect_string=r"[Y/N]", read_timeout=15)  # 发 save 并等 [Y/N] 确认提示
        conn.send_command("Y", expect_string=r"[<>\]\]", read_timeout=15)  # 回复 Y 确认并等回到提示符
        return "已执行 save"  # 保存成功说明
    except Exception as e:  # 捕获保存过程中的异常
        return f"save 未完成（可能需人工确认）：{e}"  # 返回失败原因


def _finish(task, status, summary, detail):  # 完成任务记录的统一入口
    task.status = status  # 更新状态
    task.summary = summary  # 更新摘要
    task.result_detail = detail  # 更新完整输出
    task.finished_at = datetime.now()  # 记录完成时间
    db.session.commit()  # 提交到数据库


def _get_task(task_id):  # 按主键取任务对象
    return db.session.get(TaskLog, task_id)  # 查询并返回任务记录


# ---- 任务 1：一键备份所有交换机配置 ----
def run_backup(task_id):  # 备份任务入口，接收 task_id
    task = _get_task(task_id)  # 取任务记录
    devices = Device.query.filter_by(enabled=True).all()  # 查询所有启用设备
    if not devices:  # 没有启用设备
        _finish(task, "failed", "没有启用的设备", "请先在「设备管理」中添加并启用设备。")  # 标记失败
        return  # 直接结束

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)  # 确保备份目录存在
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")  # 生成时间戳（精确到秒）
    lines, success, failed = [], 0, 0  # 结果行列表、成功计数、失败计数

    for d in devices:  # 遍历每台设备
        try:  # 尝试备份，单台失败不影响其它
            with connect_device(d) as conn:  # 建立连接（with 自动关闭）
                config = conn.send_command("display current-configuration")  # 下发命令取 running-config
            filename = f"{d.name}_{timestamp}.cfg"  # 生成备份文件名
            (BACKUP_DIR / filename).write_text(config, encoding="utf-8")  # 将配置写入文件
            lines.append(f"[成功] {d.name} ({d.ip_address}) -> {filename}")  # 记录成功行
            success += 1  # 成功计数 +1
        except Exception as e:  # 捕获异常
            lines.append(f"[失败] {d.name} ({d.ip_address}) -> {e}")  # 记录失败行
            failed += 1  # 失败计数 +1

    status = "success" if failed == 0 else ("partial" if success else "failed")  # 根据成败比例定状态
    _finish(task, status, f"备份完成：成功 {success} 台，失败 {failed} 台", "\n".join(lines))  # 汇总并写回


# ---- 任务 2：批量创建 VLAN ----
def run_create_vlans(task_id, device_id, vlan_start, vlan_end):  # 建 VLAN 任务入口
    task = _get_task(task_id)  # 取任务记录
    device = db.session.get(Device, device_id)  # 按 ID 取目标设备
    if not device:  # 设备不存在
        _finish(task, "failed", "设备不存在", f"设备 ID {device_id} 不存在。")  # 标记失败
        return  # 结束
    if not (1 <= vlan_start <= vlan_end <= 4094):  # 校验 VLAN 范围合法（1~4094 且 start<=end）
        _finish(task, "failed", "VLAN 范围非法",  # 标记失败
                f"范围应为 1~4094 且 start <= end，收到 {vlan_start}~{vlan_end}")  # 说明原因
        return  # 结束

    try:  # 尝试执行
        with connect_device(device) as conn:  # 连接目标设备
            output = conn.send_config_set([f"vlan batch {vlan_start} to {vlan_end}"])  # 下发批量建 VLAN 命令
            save_out = _save_config(conn)  # 尝试保存配置
        count = vlan_end - vlan_start + 1  # 计算 VLAN 数量
        detail = (f"下发命令：\n  vlan batch {vlan_start} to {vlan_end}\n\n"  # 明细开头：下发命令
                  f"设备输出：\n{output}\n\n{save_out}")  # 明细：设备输出 + 保存结果
        _finish(task, "success",  # 标记成功
                f"已在 {device.name} 上批量创建 VLAN {vlan_start}~{vlan_end}（共 {count} 个）", detail)  # 摘要 + 明细
    except Exception as e:  # 捕获异常
        _finish(task, "failed", f"VLAN 创建失败：{e}", str(e))  # 标记失败


# ---- 任务 3：端口安全策略扫描 ----
def parse_port_security(output):  # 解析端口安全输出为结构化数据
    """从 display port-security 输出中解析接口与端口安全启用状态。"""
    rows = []  # 结果行列表
    for line in output.splitlines():  # 按行遍历输出
        line = line.strip()  # 去掉首尾空白
        if not line:  # 空行跳过
            continue
        if re.match(r"^(GigabitEthernet|Ethernet|Eth-Trunk|GE|XGE|10GE|25GE|Vlanif)", line):  # 只处理接口数据行
            enabled = "enable" in line.lower() and "disable" not in line.lower()  # 判断是否启用端口安全
            rows.append({"interface": line.split()[0], "enabled": enabled, "raw": line})  # 记录接口名、状态、原文
    return rows  # 返回解析结果


def run_port_security_scan(task_id):  # 端口安全扫描任务入口
    task = _get_task(task_id)  # 取任务记录
    devices = Device.query.filter_by(enabled=True).all()  # 查询所有启用设备
    if not devices:  # 没有启用设备
        _finish(task, "failed", "没有启用的设备", "请先添加并启用设备。")  # 标记失败
        return  # 结束

    lines, success, failed = [], 0, 0  # 结果行、成功/失败计数
    total_ifaces, total_enabled = 0, 0  # 接口总数、启用端口安全数

    for d in devices:  # 遍历每台设备
        try:  # 尝试扫描
            with connect_device(d) as conn:  # 连接设备
                output = conn.send_command("display port-security")  # 下发命令获取端口安全状态
            rows = parse_port_security(output)  # 解析输出
            total_ifaces += len(rows)  # 累加接口总数
            enabled_rows = [r for r in rows if r["enabled"]]  # 筛出启用的接口
            total_enabled += len(enabled_rows)  # 累加启用数
            lines.append(f"【{d.name}】{d.ip_address}")  # 设备标题行
            for r in rows:  # 逐接口输出
                lines.append(f"  - {r['interface']}: {'启用' if r['enabled'] else '未启用'}")  # 接口与状态
            success += 1  # 成功计数 +1
        except Exception as e:  # 捕获异常
            lines.append(f"[失败] {d.name} ({d.ip_address}) -> {e}")  # 记录失败行
            failed += 1  # 失败计数 +1

    status = "success" if failed == 0 else ("partial" if success else "failed")  # 定状态
    _finish(task, status,  # 写回任务结果
            f"扫描完成：{success} 台设备，共 {total_ifaces} 个接口，其中启用端口安全 {total_enabled} 个",
            "\n".join(lines))  # 摘要 + 明细
