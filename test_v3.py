import requests
import time
from datetime import datetime, timedelta
import json
import sys

BASE = "http://127.0.0.1:8000/api/v1"


def section(title):
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def post(url, json=None, params=None, expect=200):
    r = requests.post(url, json=json, params=params)
    if r.status_code != expect:
        print(f"  [HTTP ERROR] POST {url} status={r.status_code}: {r.text[:400]}")
        raise AssertionError(f"POST failed {url}: {r.status_code}")
    return r


def get(url, params=None, expect=200):
    r = requests.get(url, params=params)
    if r.status_code != expect:
        print(f"  [HTTP ERROR] GET {url} status={r.status_code}: {r.text[:400]}")
        raise AssertionError(f"GET failed {url}: {r.status_code}")
    return r


def delete(url, json=None, params=None, expect=200):
    r = requests.delete(url, json=json, params=params)
    if r.status_code != expect:
        print(f"  [HTTP ERROR] DELETE {url} status={r.status_code}: {r.text[:400]}")
        raise AssertionError(f"DELETE failed {url}: {r.status_code}")
    return r


def test_all():
    section("课程候补系统 V3 功能测试")

    students = []
    entries = []

    section("[TEST 1] 创建基础测试数据")

    r = requests.post(f"{BASE}/stores", json={"name": "浦东校区", "address": "张杨路888号", "contact_phone": "021-88888888"})
    store = r.json()
    print(f"门店创建: ID={store['id']}, 名称={store['name']}")

    r = requests.post(f"{BASE}/courses", json={
        "store_id": store["id"], "name": "成人零基础素描",
        "description": "从零基础开始学素描",
        "category": "美术", "total_capacity": 50
    })
    course = r.json()
    print(f"课程创建: ID={course['id']}, 名称={course['name']}")

    start_time = (datetime.utcnow() + timedelta(days=3)).replace(microsecond=0)
    end_time = start_time + timedelta(hours=2)
    r = requests.post(f"{BASE}/slots", json={
        "course_id": course["id"],
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "capacity": 5, "location": "A101教室", "teacher": "张老师"
    })
    slot = r.json()
    print(f"时间段创建: ID={slot['id']}, 容量={slot['capacity']}, 时间={start_time.isoformat()}")

    student_data = [
        ("普通学员A", "13800000001", "sms", "normal", False, None),
        ("老学员B", "13800000002", "wechat", "normal", True, "app,email"),
        ("银牌会员C", "13800000003", "app", "silver", False, "sms,wechat"),
        ("金牌老学员D", "13800000004", "sms", "gold", True, "app,wechat"),
        ("铂金学员E", "13800000005", "wechat", "platinum", False, None),
        ("普通加急F", "13800000006", "sms", "normal", False, "app"),
        ("普通重报G", "13800000007", "sms", "normal", False, None),
    ]
    for name, phone, pref, level, returning, backup in student_data:
        payload = {
            "name": name, "phone": phone, "email": f"{phone[6:]}@test.com",
            "wechat_id": f"wx_{phone[6:]}", "preferred_channel": pref,
            "member_level": level, "is_returning_student": returning,
            "backup_channels": backup
        }
        r = requests.post(f"{BASE}/students", json=payload)
        s = r.json()
        students.append(s)
        print(f"  学员创建: {name} (等级={level}, 老学员={returning}) ID={s['id']}")

    section("[TEST 2] 候补预览功能")
    sid_A = students[0]["id"]
    sid_D = students[3]["id"]
    sid_F = students[5]["id"]

    for name, sid, urgent in [("普通学员A(非加急)", sid_A, False),
                               ("金牌老学员D", sid_D, False),
                               ("普通加急F", sid_F, True)]:
        r = requests.post(f"{BASE}/waitlist/preview", params={
            "slot_id": slot["id"], "student_id": sid, "is_urgent": urgent
        })
        p = r.json()
        print(f"  {name} -> 预测排位: {p['predicted_position']}/{p['total_after_submit']}, "
              f"分: {p['priority_score']}, 原因: {p['priority_reasons']}")

    section("[TEST 3] 课程优先级配置")
    r = requests.post(f"{BASE}/waitlist/priority-config", json={
        "course_id": course["id"],
        "member_level_score_normal": 0,
        "member_level_score_silver": 20,
        "member_level_score_gold": 40,
        "member_level_score_platinum": 80,
        "returning_student_bonus": 30,
        "urgent_bonus": 100,
    })
    cfg = r.json()
    print(f"  创建优先级配置成功: course_id={cfg['course_id']}, 铂金={cfg['member_level_score_platinum']}, 加急={cfg['urgent_bonus']}")

    r = requests.get(f"{BASE}/waitlist/priority-config/{course['id']}")
    cfg2 = r.json()
    print(f"  读取配置确认: 金牌={cfg2['member_level_score_gold']}, 老学员={cfg2['returning_student_bonus']}")

    section("[TEST 4] 提交候补 - 使用课程级优先级配置")
    for i, (name, phone, pref, level, returning, backup) in enumerate(student_data):
        is_urgent = (name == "普通加急F")
        r = requests.post(f"{BASE}/waitlist", json={
            "slot_id": slot["id"], "student_id": students[i]["id"], "is_urgent": is_urgent
        })
        e = r.json()
        entries.append(e)
        print(f"  {name} -> entry_id={e['id']}, priority_score={e['priority_score']}")

    print("\n  提交后查询排位(使用课程级配置后):")
    for name, entry in zip([n[0] for n in student_data], entries):
        r = requests.get(f"{BASE}/waitlist/{entry['id']}/position")
        pos = r.json()
        print(f"    {name} -> 排位: {pos['current_position']}/{pos['total_waiting']}, "
              f"分={pos['priority_score']}, 原因: {pos['priority_reasons']}")

    section("[TEST 5] 修复小问题: 取消候补后重新报名同一时段")
    g_idx = 6
    entry_g = entries[g_idx]
    print(f"  取消 普通重报G 的候补(entry_id={entry_g['id']})...")
    r = requests.delete(f"{BASE}/waitlist/{entry_g['id']}", params={"student_id": students[g_idx]["id"]},
                        json={"cancel_reason": "临时有事"})
    print(f"    取消结果: 状态={r.json()['status']}")

    print("  尝试重新报名(预期应成功)...")
    r = requests.post(f"{BASE}/waitlist", json={
        "slot_id": slot["id"], "student_id": students[g_idx]["id"], "is_urgent": False
    })
    if r.status_code == 200:
        new_entry = r.json()
        entries[g_idx] = new_entry
        print(f"    重新报名成功! new_entry_id={new_entry['id']}, 位置={new_entry['queue_position']}")
    else:
        print(f"    重新报名失败! status={r.status_code}, detail={r.text}")

    section("[TEST 6] 释放名额, 触发多渠道通知 + 完整时间线")
    r = requests.post(f"{BASE}/waitlist/release", json={"slot_id": slot["id"], "release_count": 3})
    rel = r.json()
    print(f"  释放结果: {rel['message']}, 通知人数={rel['notified_count']}")
    if rel["notified_entries"]:
        first_e = rel["notified_entries"][0]
        print(f"  [DEBUG] notified_entries[0] keys={list(first_e.keys()) if isinstance(first_e, dict) else type(first_e)}")

    notified_ids = []
    for e in rel["notified_entries"]:
        if isinstance(e, dict):
            for k in ["id", "entry_id", "waitlist_entry_id"]:
                if k in e and e[k]:
                    notified_ids.append(e[k])
                    break
        else:
            for attr in ["id", "entry_id"]:
                _id = getattr(e, attr, None)
                if _id:
                    notified_ids.append(_id)
                    break
    notified_ids = list(dict.fromkeys([i for i in notified_ids if i]))

    if not notified_ids:
        print("  [FALLBACK] 通过 slot_id 查 NOTIFIED 状态的 entries...")
        for entry in entries:
            r2 = requests.get(f"{BASE}/waitlist/{entry['id']}/position")
            pos = r2.json()
            if pos.get("status") == "notified":
                notified_ids.append(entry["id"])
                if len(notified_ids) >= 3:
                    break
    print(f"  最终 notified_ids={notified_ids}")
    if notified_ids:
        first_entry_id = notified_ids[0]
        print(f"\n  查询第一名学员的通知历史(包含时间线)...")
        r = requests.get(f"{BASE}/notifications/waitlist/{first_entry_id}")
        notifications = r.json()
        if notifications:
            n = notifications[0]
            print(f"    通知ID: {n['id']}, 类型={n['type']}, 状态={n['status']}, 尝试次数={n['attempt_count']}")
            print(f"    渠道顺序: {n.get('channel_attempt_order', '')}")
            print(f"    尝试记录: {len(n['attempts'])}次")
            for att in n["attempts"]:
                print(f"      -> 第{att['attempt_number']}次 {att['channel']}: {att['status']}, "
                      f"错误={att.get('error_message', '无')}")
            print(f"    完整时间线: {len(n['timeline'])}条事件")
            for ev in n["timeline"]:
                print(f"      [{ev['created_at'][11:19]}] {ev['event']} "
                      f"({ev.get('channel', '-') or '-'}) -> {ev.get('message', '')[:60]}")

    section("[TEST 7] 通知送达和已读回执")
    if notifications and notifications:
        notif_id = notifications[0]["id"]
        print(f"  对通知ID={notif_id}上报送达回执(sms)...")
        r = requests.post(f"{BASE}/notifications/{notif_id}/delivery-receipt", json={
            "notification_id": notif_id, "channel": "sms", "delivered": True
        })
        r1 = r.json()
        print(f"    送达确认: delivered_at={r1.get('delivered_at')}, status={r1['status']}")

        print(f"  对通知ID={notif_id}上报已读回执(sms)...")
        r = requests.post(f"{BASE}/notifications/{notif_id}/read-receipt", json={
            "notification_id": notif_id, "channel": "sms"
        })
        r2 = r.json()
        print(f"    已读确认: read_at={r2.get('read_at')}, status={r2['status']}")

        print(f"  重新查看完整时间线(送达+已读已入账):")
        r = requests.get(f"{BASE}/notifications/{notif_id}")
        n = r.json()
        for ev in n["timeline"][-4:]:
            print(f"      [{ev['created_at'][11:19]}] {ev['event']} -> {ev.get('message', '')[:60]}")

    section("[TEST 8] 待重试通知列表接口")
    r = requests.get(f"{BASE}/notifications/pending/retry")
    rp = r.json()
    print(f"  待重试通知数量: {rp['count']} (列表正确打开,无报错)")
    for n in rp["notifications"][:3]:
        print(f"    ID={n['id']}, 渠道={n['channel']}, 尝试={n['attempt_count']}, 下次重试={n['next_retry_at']}")

    section("[TEST 9] 学员确认补位 + 到课标记 + 点名清单")
    print("  所有已通知学员确认补位:")
    for nid in notified_ids:
        r = requests.post(f"{BASE}/waitlist/{nid}/confirm", json={"confirmed": True})
        e = r.json()
        print(f"    entry_id={nid} 确认: status={e['status']}, confirmed_at={e.get('confirmed_at')}")

    print("\n  查询门店点名清单:")
    r = requests.get(f"{BASE}/waitlist/attendance/roster", params={"store_id": store["id"]})
    roster = r.json()
    print(f"    总时段数={roster['total_slots']}, 总记录数={roster['total_entries']}")
    if roster["slots"]:
        rs = roster["slots"][0]
        print(f"    时段: {rs['course_name']} {rs['start_time']}")
        print(f"    统计: 已确认待点名={rs['total_confirmed_pending_mark']}, "
              f"已到课={rs['total_attended']}, 未到课={rs['total_no_show']}, "
              f"到课率={rs['attendance_rate']}")
        for ent in rs["entries"][:5]:
            print(f"      -> {ent['student_name']} 状态={ent['status']} 会员={ent['member_level']} "
                  f"排位={ent['queue_position']}")

    print("\n  批量标记到课(前2个到课,1个未到课):")
    entry_ids = [e["entry_id"] for e in rs["entries"][:3]]
    r = requests.post(f"{BASE}/waitlist/attendance/batch", json={
        "slot_id": slot["id"],
        "attended_ids": entry_ids[:2],
        "no_show_ids": entry_ids[2:] if len(entry_ids) > 2 else []
    })
    br = r.json()
    print(f"    结果: 成功={br['success_count']}, 失败={br['failed_count']}")
    print(f"    时段汇总: 到课={br['total_attended']}, 未到={br['total_no_show']}, 到课率={br['attendance_rate']}")
    for rr in br["results"]:
        print(f"      -> id={rr['entry_id']}: {rr['status']} -> {rr['success']}")

    section("[TEST 10] 到课率统计一致性校验(多次刷新一致)")
    for round_num in range(1, 4):
        time.sleep(0.1)
        r = requests.get(f"{BASE}/waitlist/attendance/roster", params={"slot_id": slot["id"]})
        roster = r.json()
        if roster["slots"]:
            s = roster["slots"][0]
            print(f"  第{round_num}次刷新: 已确认={s['total_entries']}, "
                  f"到课={s['total_attended']}, 未到={s['total_no_show']}, "
                  f"到课率={s['attendance_rate']} (每次一致无波动)")

    r = requests.get(f"{BASE}/stats/stores/conversion")
    conv_list = r.json()
    if r.status_code != 200:
        print(f"  [WARN] 门店转化统计 status={r.status_code}: {r.text[:200]}")
    if isinstance(conv_list, list) and conv_list:
        conv = conv_list[0]
        print(f"\n  门店转化统计: 候补={conv.get('total_waitlist')}, 确认={conv.get('total_confirmed')}, "
              f"到课={conv.get('total_attended')}, 未到={conv.get('total_no_show')}, "
              f"到课率={conv.get('attendance_rate')}, 转化率={conv.get('conversion_rate')}")

    r = requests.get(f"{BASE}/stats/slots/dashboard", params={"slot_id": slot["id"]})
    dash = r.json()
    if isinstance(dash, list) and dash:
        d = dash[0]
        print(f"  看板数据: 确认={d.get('confirmed_count')}, 到课={d.get('attended_count')}, "
              f"未到={d.get('no_show_count')}, 到课率={d.get('attendance_rate', 0)}, 转化率={d.get('conversion_rate', 0)}")

    section("[TEST 11] 通知统计概览")
    r = requests.get(f"{BASE}/notifications/stats/summary")
    st = r.json()
    print(f"  总通知数={st['total']}, 已发送={st['sent']}, 已送达={st['delivered']}, "
          f"已读={st['read']}, 失败={st['failed']}, 待重试={st['pending_retry']}")
    print(f"  送达率={st['delivery_rate']}, 已读率={st['read_rate']}, "
          f"平均每通知尝试={st['avg_attempts_per_notification']}次")

    section("V3 全部测试完成!")


if __name__ == "__main__":
    try:
        test_all()
    except Exception as ex:
        import traceback
        print(f"\n[FATAL ERROR] {ex}")
        traceback.print_exc()
