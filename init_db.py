"""建表 + 预置示例设备。首次使用执行一次：python init_db.py"""
from app import app  # 导入 Flask 应用实例（含配置与路由）
from models import db, Device  # 导入数据库实例与设备模型


def main():  # 初始化入口函数
    with app.app_context():  # 进入应用上下文，才能使用数据库
        db.create_all()  # 根据模型自动建表（已存在的表不会重复创建）

        # 预置 2 台示例设备，方便模拟模式下直接点按钮演示（仅在空库时插入）
        if Device.query.count() == 0:  # 设备表为空时才插入，避免重复
            db.session.add_all([  # 批量加入两条设备记录
                Device(name="SW-01", ip_address="192.168.1.1", username="admin",  # 第一台示例设备
                       password="Admin@123", device_type="huawei_vrp", enabled=True),  # 其凭证与类型
                Device(name="SW-02", ip_address="192.168.1.2", username="admin",  # 第二台示例设备
                       password="Admin@123", device_type="huawei_vrp", enabled=True),  # 其凭证与类型
            ])
            db.session.commit()  # 提交事务，把示例设备写入数据库
            print("已预置 2 台示例设备：SW-01、SW-02")  # 打印预置提示

        print("数据库初始化完成。")  # 打印完成提示


if __name__ == "__main__":  # 仅当直接运行本脚本时执行
    main()  # 调用初始化函数
