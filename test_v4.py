import requests
import time
from datetime import datetime, timedelta
import json
import sys

BASE = "http://127.0.0.1:8000/api/v1"


def section(title):
    print("\n" + "=" * 60 + "\n" + title + "\n" + "=" * 60)


def post(url, json=None, params=None, expect=200):
    r = requests.post(url, json=json, params=params)
    if r.status_code != expect:
        print("  [HTTP ERROR] POST " + url + " status=" + str(r.status_code) + ": " + r.text[:400])
        raise AssertionError("POST failed " + url + ": " + str(r.status_code))
    return r


def get(url, params=None, expect=200):
    r = requests.get(url, params=params)
    if r.status_code != expect:
        print("  [HTTP ERROR] GET " + url + " status=" + str(r.status_code) + ": " + r.text[:400])
        raise AssertionError("GET failed " + url + ": " + str(r.status_code))
    return r


def delete(url, json=None, params=None, expect=200):
    r = requests.delete(url, json=json, params=params)
    if r.status_code != expect:
        print("  [HTTP ERROR] DELETE " + url + " status=" + str(r.status_code) + ": " + r.text[:400])
        raise AssertionError("DELETE failed " + url + ": " + str(r.status_code))
    return r


def put(url, json=None, params=None, expect=200):
    r = requests.put(url, json=json, params=params)
    if r.status_code != expect:
        print("  [HTTP ERROR] PUT " + url + " status=" + str(r.status_code) + ": " + r.text[:400])
        raise AssertionError("PUT failed " + url + ": " + str(r.status_code))
    return r


def test_all():
    section("V4 Function Test")

    students = []
    entries = []

    section("[TEST 1] Create base test data")

    r = post(BASE + "/stores", json={"name": "Pudong Campus", "address": "888 Zhangyang Rd", "contact_phone": "021-88888888"})
    store = r.json()
    print("Store created: ID=" + str(store["id"]) + ", name=" + store["name"])

    r = post(BASE + "/courses", json={
        "store_id": store["id"], "name": "Adult Beginner Sketch",
        "description": "Learn sketch from scratch",
        "category": "Art", "total_capacity": 50
    })
    course = r.json()
    print("Course created: ID=" + str(course["id"]) + ", name=" + course["name"])

    start_time = (datetime.utcnow() + timedelta(days=3)).replace(microsecond=0)
    end_time = start_time + timedelta(hours=2)
    r = post(BASE + "/slots", json={
        "course_id": course["id"],
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "capacity": 5, "location": "Room A101", "teacher": "Teacher Zhang"
    })
    slot = r.json()
    print("Slot created: ID=" + str(slot["id"]) + ", capacity=" + str(slot["capacity"]) + ", time=" + start_time.isoformat())

    student_data = [
        ("Student A", "13800000021", "sms", "normal", False, None),
        ("Returning B", "13800000022", "wechat", "normal", True, "app,email"),
        ("Silver C", "13800000023", "app", "silver", False, "sms,wechat"),
        ("Gold Returning D", "13800000024", "sms", "gold", True, "app,wechat"),
        ("Platinum E", "13800000025", "wechat", "platinum", False, None),
        ("Urgent F", "13800000026", "sms", "normal", False, "app"),
    ]
    for name, phone, pref, level, returning, backup in student_data:
        payload = {
            "name": name, "phone": phone, "email": phone[6:] + "@test.com",
            "wechat_id": "wx_" + phone[6:], "preferred_channel": pref,
            "member_level": level, "is_returning_student": returning,
            "backup_channels": backup
        }
        r = post(BASE + "/students", json=payload)
        s = r.json()
        students.append(s)
        print("  Student created: " + name + " (level=" + level + ", returning=" + str(returning) + ") ID=" + str(s["id"]))

    section("[TEST 2] Create initial priority config")
    r = post(BASE + "/waitlist/priority-config", json={
        "course_id": course["id"],
        "member_level_score_normal": 0,
        "member_level_score_silver": 10,
        "member_level_score_gold": 20,
        "member_level_score_platinum": 30,
        "returning_student_bonus": 15,
        "urgent_bonus": 50,
    })
    cfg = r.json()
    print("  Initial config: platinum=30, urgent=50")

    section("[TEST 3] Students join waitlist (initial config)")
    for i, (name, phone, pref, level, returning, backup) in enumerate(student_data):
        is_urgent = (name == "Urgent F")
        r = post(BASE + "/waitlist", json={
            "slot_id": slot["id"], "student_id": students[i]["id"], "is_urgent": is_urgent
        })
        e = r.json()
        entries.append(e)
        print("  " + name + " -> entry_id=" + str(e["id"]) + ", priority_score=" + str(e["priority_score"]))

    print("\n  Initial ranking (urgent50 > platinum30 > gold_returning35 > returning15 > silver10 > normal0):")
    for name, entry in zip([n[0] for n in student_data], entries):
        r = get(BASE + "/waitlist/" + str(entry["id"]) + "/position")
        pos = r.json()
        print("    " + name + " -> position: " + str(pos["current_position"]) + "/" + str(pos["total_waiting"]) + ", score=" + str(pos["priority_score"]))

    section("[TEST 4] Priority config change + real-time refresh (Requirement 4)")
    print("  Current platinum=30, urgent=50")
    print("  Update platinum to 80, urgent to 100, operator=admin, source=web")

    r = put(BASE + "/waitlist/priority-config/" + str(course["id"]), json={
        "member_level_score_platinum": 80,
        "urgent_bonus": 100,
        "operator_id": "admin_001",
        "operator_name": "System Admin",
        "source": "web_console",
    })
    cfg2 = r.json()
    print("  Config updated: platinum=" + str(cfg2["member_level_score_platinum"]) + ", urgent=" + str(cfg2["urgent_bonus"]))

    print("\n  Ranking after config change (should auto-refresh):")
    for name, entry in zip([n[0] for n in student_data], entries):
        r = get(BASE + "/waitlist/" + str(entry["id"]) + "/position")
        pos = r.json()
        print("    " + name + " -> position: " + str(pos["current_position"]) + "/" + str(pos["total_waiting"]) + ", score=" + str(pos["priority_score"]))

    print("\n  [Verify] Urgent F(100) should be #1, Platinum E(80) should be #2:")
    pos_list = []
    for name, entry in zip([n[0] for n in student_data], entries):
        r = get(BASE + "/waitlist/" + str(entry["id"]) + "/position")
        pos = r.json()
        pos_list.append((name, pos["current_position"], pos["priority_score"]))
    pos_list.sort(key=lambda x: x[1])
    assert pos_list[0][0] == "Urgent F" and pos_list[0][2] == 100, "Urgent F should be #1, actual: " + str(pos_list[0])
    assert pos_list[1][0] == "Platinum E" and pos_list[1][2] == 80, "Platinum E should be #2, actual: " + str(pos_list[1])
    print("  OK Ranking correct: Urgent F(100) #1, Platinum E(80) #2")

    section("[TEST 5] Release slots (notify in refreshed order)")
    r = post(BASE + "/waitlist/release", json={"slot_id": slot["id"], "release_count": 3})
    rel = r.json()
    print("  Release result: " + rel["message"] + ", notified_count=" + str(rel["notified_count"]))

    notified_ids = []
    for e in rel["notified_entries"]:
        if isinstance(e, dict):
            if "id" in e:
                notified_ids.append(e["id"])
            elif "entry_id" in e:
                notified_ids.append(e["entry_id"])
        else:
            _id = getattr(e, "id", None) or getattr(e, "entry_id", None)
            if _id:
                notified_ids.append(_id)
    notified_ids = list(dict.fromkeys([i for i in notified_ids if i]))

    if not notified_ids:
        for entry in entries:
            r2 = get(BASE + "/waitlist/" + str(entry["id"]) + "/position")
            pos = r2.json()
            if pos.get("status") == "notified":
                notified_ids.append(entry["id"])
                if len(notified_ids) >= 3:
                    break
    print("  Notified entry_ids: " + str(notified_ids))

    names_map = {e["id"]: n for n, e in zip([n[0] for n in student_data], entries)}
    print("  Notified students (should be in refreshed order): " + str([names_map.get(i, "?") for i in notified_ids]))
    assert notified_ids[0] == entries[5]["id"], "First should be Urgent F, actual: " + names_map.get(notified_ids[0], "?")
    assert notified_ids[1] == entries[4]["id"], "Second should be Platinum E, actual: " + names_map.get(notified_ids[1], "?")
    print("  OK Release notifies in refreshed order: Urgent F -> Platinum E -> Gold Returning D")

    section("[TEST 6] Notification receipt stabilization (Requirement 3)")
    first_notif_entry = notified_ids[0]
    r = get(BASE + "/notifications/waitlist/" + str(first_notif_entry))
    notifs = r.json()
    invitation_notif = None
    for n in notifs:
        if n.get("type") == "invitation" or (isinstance(n.get("type"), str) and "invitation" in n.get("type")):
            invitation_notif = n
            break
    if invitation_notif is None and notifs:
        invitation_notif = notifs[0]

    if invitation_notif:
        notif_id = invitation_notif["id"]
        print("  Test notification ID=" + str(notif_id) + ": report READ first, then DELIVERY")
        print("  Current timeline count: " + str(len(invitation_notif.get("timeline", []))))

        r = post(BASE + "/notifications/" + str(notif_id) + "/read-receipt", json={
            "notification_id": 99999,
            "channel": "sms",
        })
        read_result = r.json()
        print("  [Verify] Request body notification_id=99999 (wrong), but入账 by path param " + str(notif_id))
        print("  Read receipt: delivered_at=" + str(read_result["delivered_at"]) + ", read_at=" + str(read_result["read_at"]) + ", status=" + read_result["status"])
        assert read_result["id"] == notif_id, "Should入账 by path param " + str(notif_id) + ", actual id=" + str(read_result["id"])
        assert read_result["delivered_at"] is not None, "Should auto-fill delivered_at"
        assert read_result["read_at"] is not None, "Should have read_at"
        print("  OK入账 by path param id, auto-fill delivery when READ comes first")

        r = get(BASE + "/notifications/" + str(notif_id))
        notif_detail = r.json()
        timeline = notif_detail.get("timeline", [])
        event_names = [t.get("event") for t in timeline]
        print("  Timeline events: " + str(event_names))
        if "delivered" in event_names and "read" in event_names:
            delivered_idx = event_names.index("delivered")
            read_idx = event_names.index("read")
            assert delivered_idx < read_idx, "delivered should come before read, actual order: " + str(event_names)
            print("  OK Timeline order correct: delivered -> read")

    section("[TEST 7] Students confirm waitlist")
    for eid in notified_ids:
        r = post(BASE + "/waitlist/" + str(eid) + "/confirm", json={"confirmed": True})
        conf = r.json()
        print("  entry_id=" + str(eid) + " confirmed: status=" + conf["status"] + ", confirmed_at=" + str(conf["confirmed_at"]))

    section("[TEST 8] Batch mark attendance")
    r = post(BASE + "/waitlist/attendance/batch", json={
        "slot_id": slot["id"],
        "attended_ids": [notified_ids[0], notified_ids[1]],
        "no_show_ids": [notified_ids[2]],
    })
    batch = r.json()
    print("  Batch mark: success=" + str(batch["success_count"]) + ", failed=" + str(batch["failed_count"]))
    print("  Summary: attended=" + str(batch["total_attended"]) + ", no_show=" + str(batch["total_no_show"]) + ", rate=" + str(batch["attendance_rate"]))

    section("[TEST 9] Operation audit logs (Requirement 2)")
    print("  Query audit logs by student_id (Urgent F, student_id=" + str(students[5]["id"]) + "):")
    r = get(BASE + "/waitlist/audit-logs", params={"student_id": students[5]["id"]})
    audit = r.json()
    print("  Total " + str(audit["total"]) + " records:")
    for log in audit["items"]:
        status_prev = log.get("previous_status", "") or ""
        status_new = log.get("new_status", "") or ""
        details = log.get("details", "") or ""
        print("    [" + log["created_at"][11:19] + "] " + log["action"].ljust(25) + " " + log["student_name"].ljust(15) + " " +
              status_prev.ljust(12) + " -> " + status_new.ljust(12) + " " + details)

    action_types = {log["action"] for log in audit["items"]}
    print("\n  Action types found: " + str(sorted(action_types)))
    expected_actions = {"created", "priority_recalculated", "notified", "confirmed", "attended"}
    for act in expected_actions:
        assert act in action_types, "Missing action type: " + act
    print("  OK All key operations audited: created -> priority_recalculated -> notified -> confirmed -> attended")

    print("\n  Query audit logs by slot_id (slot_id=" + str(slot["id"]) + "):")
    r = get(BASE + "/waitlist/audit-logs", params={"slot_id": slot["id"], "limit": 200})
    audit_slot = r.json()
    print("  Total " + str(audit_slot["total"]) + " records, covers all students")
    assert audit_slot["total"] >= 15, "Should have at least 15 records, actual: " + str(audit_slot["total"])
    print("  OK Slot-level audit logs can be fully retrieved")

    section("[TEST 10] Waitlist funnel daily report (Requirement 1)")
    r = get(BASE + "/waitlist/funnel/daily", params={"slot_id": slot["id"]})
    funnel = r.json()
    print("  Funnel report: records=" + str(funnel["total_records"]))
    print("  Summary: waitlist=" + str(funnel["summary"]["total_waitlist"]) +
          ", notified=" + str(funnel["summary"]["total_notified"]) +
          ", delivered=" + str(funnel["summary"]["total_delivered"]) +
          ", read=" + str(funnel["summary"]["total_read"]) +
          ", confirmed=" + str(funnel["summary"]["total_confirmed"]) +
          ", attended=" + str(funnel["summary"]["total_attended"]) +
          ", no_show=" + str(funnel["summary"]["total_no_show"]))
    print("  Conversion rate: " + str(funnel["summary"]["avg_conversion_rate"]) +
          ", attendance rate: " + str(funnel["summary"]["avg_attendance_rate"]))

    if funnel["data"]:
        d = funnel["data"][0]
        print("\n  Detail: " + d["course_name"] + " " + str(d["slot_start_time"]))
        print("    waitlist=" + str(d["total_waitlist"]) + ", notified=" + str(d["total_notified"]) + ", notification_rate=" + str(d["notification_rate"]))
        print("    delivered=" + str(d["total_delivered"]) + ", delivery_rate=" + str(d["delivery_rate"]))
        print("    read=" + str(d["total_read"]) + ", read_rate=" + str(d["read_rate"]))
        print("    confirmed=" + str(d["total_confirmed"]) + ", confirmation_rate=" + str(d["confirmation_rate"]))
        print("    attended=" + str(d["total_attended"]) + ", no_show=" + str(d["total_no_show"]) + ", attendance_rate=" + str(d["attendance_rate"]))

    print("\n  [Consistency Verify] Multiple refreshes, same stats:")
    for i in range(1, 4):
        time.sleep(0.05)
        r = get(BASE + "/waitlist/funnel/daily", params={"slot_id": slot["id"]})
        f2 = r.json()
        print("  Refresh #" + str(i) + ": waitlist=" + str(f2["summary"]["total_waitlist"]) +
              ", confirmed=" + str(f2["summary"]["total_confirmed"]) +
              ", attended=" + str(f2["summary"]["total_attended"]) +
              ", rate=" + str(f2["summary"]["avg_attendance_rate"]))
        assert f2["summary"]["total_waitlist"] == funnel["summary"]["total_waitlist"]
        assert f2["summary"]["total_attended"] == funnel["summary"]["total_attended"]
        assert f2["summary"]["avg_attendance_rate"] == funnel["summary"]["avg_attendance_rate"]
    print("  OK Multiple refreshes produce identical stats, no fluctuation")

    print("\n  Export funnel CSV...")
    r = get(BASE + "/stats/funnel/daily/export.csv", params={"slot_id": slot["id"]})
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
    csv_lines = r.text.strip().split("\n")
    print("  CSV has " + str(len(csv_lines)) + " lines, header=" + csv_lines[0][:80] + "...")
    print("  OK CSV export successful")

    section("[TEST 11] Verify /stats path returns same data")
    r = get(BASE + "/stats/funnel/daily", params={"slot_id": slot["id"]})
    funnel2 = r.json()
    assert funnel2["total_records"] == funnel["total_records"]
    assert funnel2["summary"]["total_waitlist"] == funnel["summary"]["total_waitlist"]
    assert funnel2["summary"]["total_attended"] == funnel["summary"]["total_attended"]
    print("  OK /stats/funnel/daily and /waitlist/funnel/daily return identical data")

    section("[TEST 12] Manual priority refresh endpoint")
    r = post(BASE + "/waitlist/priority-config/" + str(course["id"]) + "/refresh", params={
        "operator_id": "admin_002",
        "operator_name": "Operation Manager",
        "source": "manual",
    })
    refresh = r.json()
    print("  Manual refresh: checked=" + str(refresh["total_checked"]) +
          ", updated=" + str(refresh["total_updated"]) +
          ", slots=" + str(refresh["slots_refreshed"]))
    print("  OK Manual refresh endpoint works")

    section("V4 All tests passed!")


if __name__ == "__main__":
    try:
        test_all()
    except Exception as ex:
        import traceback
        print("\n[FATAL ERROR] " + str(ex))
        traceback.print_exc()
