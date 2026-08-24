"""建表 + 预置示例设备。首次使用执行一次：python init_db.py"""
from app import app
from models import db, Device


def main():
    with app.app_context():
        db.create_all()

        # 预置 2 台示例设备，方便模拟模式下直接点按钮演示（仅在空库时插入）
        if Device.query.count() == 0:
            db.session.add_all([
                Device(name="SW-01", ip_address="192.168.1.1", username="admin",
                       password="Admin@123", device_type="huawei_vrp", enabled=True),
                Device(name="SW-02", ip_address="192.168.1.2", username="admin",
                       password="Admin@123", device_type="huawei_vrp", enabled=True),
            ])
            db.session.commit()
            print("已预置 2 台示例设备：SW-01、SW-02")

        print("数据库初始化完成。")


if __name__ == "__main__":
    main()
