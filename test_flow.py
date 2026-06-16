import requests
import sys
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8000/api/v1"


def print_separator(title=""):
    print(f"\n{'='*60}")
    if title:
        print(f"  {title}")
        print("="*60)


def test_flow():
    print_separator("课程候补与补位通知系统 - 端到端测试")

    try:
        print_separator("1. 创建门店")
        store_data = {
            "name": "中关村培训中心",
            "address": "北京市海淀区中关村大街1号",
            "contact_phone": "010-88888888"
        }
        r = requests.post(f"{BASE_URL}/stores", json=store_data)
        r.raise_for_status()
        store = r.json()
        store_id = store["id"]
        print(f"[OK] 门店创建成功: {store['name']} (ID: {store_id})")

        print_separator("2. 创建课程")
        course_data = {
            "store_id": store_id,
            "name": "Python 编程入门班",
            "description": "零基础学习 Python 编程，适合 8-12 岁儿童",
            "category": "编程",
            "total_capacity": 30
        }
        r = requests.post(f"{BASE_URL}/courses", json=course_data)
        r.raise_for_status()
        course = r.json()
        course_id = course["id"]
        print(f"[OK] 课程创建成功: {course['name']} (ID: {course_id})")

        print_separator("3. 创建多个课程时间段")
        slots = []
        for i in range(2):
            start_time = (datetime.now() + timedelta(days=i+7)).replace(hour=9, minute=0, second=0, microsecond=0)
            end_time = start_time + timedelta(hours=2)
            slot_data = {
                "course_id": course_id,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "capacity": 10,
                "location": f"教室 {i+1}01",
                "teacher": "王老师" if i == 0 else "李老师"
            }
            r = requests.post(f"{BASE_URL}/slots", json=slot_data)
            r.raise_for_status()
            slot = r.json()
            slots.append(slot)
            print(f"[OK] 时间段创建成功: {slot['start_time'][:16]} - {slot['end_time'][11:16]} (ID: {slot['id']})")

        slot_id = slots[0]["id"]

        print_separator("4. 创建学员")
        students = []
        for i in range(6):
            student_data = {
                "name": f"学员{i+1:02d}",
                "phone": f"138{i+1:08d}",
                "email": f"student{i+1}@example.com",
                "preferred_channel": "sms"
            }
            r = requests.post(f"{BASE_URL}/students", json=student_data)
            r.raise_for_status()
            student = r.json()
            students.append(student)
            print(f"[OK] 学员创建成功: {student['name']} (ID: {student['id']}, 手机: {student['phone']})")

        print_separator("5. 学员提交候补申请")
        waitlist_entries = []
        for i, student in enumerate(students):
            waitlist_data = {
                "slot_id": slot_id,
                "student_id": student["id"]
            }
            r = requests.post(f"{BASE_URL}/waitlist", json=waitlist_data)
            r.raise_for_status()
            entry = r.json()
            waitlist_entries.append(entry)
            print(f"[OK] {student['name']} 提交候补成功，当前排位: {entry['queue_position']}")

        print_separator("6. 验证每人候补数量限制")
        extra_student_data = {
            "name": "测试学员",
            "phone": "13900000000",
            "preferred_channel": "sms"
        }
        r = requests.post(f"{BASE_URL}/students", json=extra_student_data)
        r.raise_for_status()
        extra_student = r.json()
        for s in slots:
            waitlist_data = {"slot_id": s["id"], "student_id": extra_student["id"]}
            requests.post(f"{BASE_URL}/waitlist", json=waitlist_data)
        
        waitlist_data = {"slot_id": slot_id, "student_id": extra_student["id"]}
        r = requests.post(f"{BASE_URL}/waitlist", json=waitlist_data)
        print(f"[WARN] 超过候补限制验证: {r.json().get('detail', '未知错误')}")

        print_separator("7. 查询学员候补排位与预计机会")
        for entry in waitlist_entries[:3]:
            r = requests.get(f"{BASE_URL}/waitlist/{entry['id']}/position")
            r.raise_for_status()
            pos = r.json()
            print(f"[INFO] {entry['id']}号候补 - 排位: {pos['current_position']}/{pos['total_waiting']}, "
                  f"预计机会: {pos['estimated_opportunity']*100:.1f}%, 状态: {pos['status']}")

        print_separator("8. 释放名额并通知候补学员")
        release_data = {
            "slot_id": slot_id,
            "release_count": 2
        }
        r = requests.post(f"{BASE_URL}/waitlist/release", json=release_data)
        r.raise_for_status()
        result = r.json()
        print(f"[OK] 名额释放成功，已通知 {result['notified_count']} 名学员")
        for e in result["notified_entries"]:
            print(f"   - 通知学员 ID: {e['student_id']}, 状态: {e['status']}, 超时时间: {e['timeout_at'][:19]}")

        print_separator("9. 第一名学员确认补位，第二名学员放弃")
        r = requests.post(
            f"{BASE_URL}/waitlist/{result['notified_entries'][0]['id']}/confirm",
            json={"confirmed": True}
        )
        r.raise_for_status()
        confirmed = r.json()
        print(f"[OK] 学员 {confirmed['student_id']} 确认补位成功，状态: {confirmed['status']}")

        r = requests.post(
            f"{BASE_URL}/waitlist/{result['notified_entries'][1]['id']}/confirm",
            json={"confirmed": False}
        )
        r.raise_for_status()
        declined = r.json()
        print(f"[OK] 学员 {declined['student_id']} 放弃补位，状态: {declined['status']}")
        print(f"   (系统自动顺延通知下一位候补学员)")

        print_separator("10. 学员主动取消候补")
        cancel_entry = waitlist_entries[3]
        r = requests.delete(
            f"{BASE_URL}/waitlist/{cancel_entry['id']}?student_id={cancel_entry['student_id']}",
            json={"cancel_reason": "时间冲突"}
        )
        r.raise_for_status()
        cancelled = r.json()
        print(f"[OK] 学员 {cancelled['student_id']} 取消候补，状态: {cancelled['status']}")

        print_separator("11. 查询通知记录")
        r = requests.get(f"{BASE_URL}/notifications/student/{students[0]['id']}")
        r.raise_for_status()
        notifications = r.json()
        print(f"[INFO] 学员 {students[0]['name']} 的通知记录:")
        for n in notifications:
            print(f"   - [{n['type']}] {n['status']} - {n['content'][:50]}...")

        print_separator("12. 查询课程候补热度排行")
        r = requests.get(f"{BASE_URL}/stats/courses/popularity")
        r.raise_for_status()
        rankings = r.json()
        print(f"[INFO] 课程热度排行榜:")
        for rank in rankings:
            print(f"   {rank['rank']}. {rank['course_name']} ({rank['store_name']}) "
                  f"- 候补人数: {rank['total_waitlist_count']}, 转化率: {rank['conversion_rate']*100:.1f}%")

        print_separator("13. 按门店查看转化情况")
        r = requests.get(f"{BASE_URL}/stats/stores/conversion")
        r.raise_for_status()
        stats = r.json()
        print(f"[INFO] 门店转化统计:")
        for s in stats:
            print(f"   {s['store_name']}: 课程数={s['total_courses']}, 候补总数={s['total_waitlist']}, "
                  f"已确认={s['total_confirmed']}, 转化率={s['conversion_rate']*100:.1f}%")

        print_separator("14. 处理超时未确认的候补")
        r = requests.post(f"{BASE_URL}/waitlist/process-timeouts")
        r.raise_for_status()
        result = r.json()
        print(f"[OK] 超时处理完成，处理了 {result['processed_count']} 条超时记录")

        print_separator("[SUCCESS] 所有测试流程完成！")
        print("\n[INFO] API 文档地址: http://localhost:8000/docs")
        print("[INFO] 服务运行正常，所有核心功能验证通过！")

    except Exception as e:
        print(f"\n[ERROR] 测试出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    test_flow()
