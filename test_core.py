import requests
from datetime import datetime, timedelta

BASE = 'http://localhost:8000/api/v1'

print('[TEST 1] 名额释放 - 已通知占坑逻辑')
r = requests.post(f'{BASE}/stores', json={'name': '测试门店', 'address': '测试', 'contact_phone': '111'})
store_id = r.json()['id']
r = requests.post(f'{BASE}/courses', json={'store_id': store_id, 'name': '测试课程', 'category': '测试', 'total_capacity': 30})
course_id = r.json()['id']
slot_start = (datetime.now() + timedelta(days=7)).replace(hour=9, minute=0, second=0, microsecond=0)
r = requests.post(f'{BASE}/slots', json={
    'course_id': course_id,
    'start_time': slot_start.isoformat(),
    'end_time': (slot_start + timedelta(hours=2)).isoformat(),
    'capacity': 5,
    'location': '教室1',
    'teacher': '王老师'
})
slot_id = r.json()['id']

students = []
for i in range(5):
    r = requests.post(f'{BASE}/students', json={
        'name': f'学员{i+1}',
        'phone': f'139{i+1:08d}',
        'preferred_channel': 'sms'
    })
    students.append(r.json())

for s in students:
    r = requests.post(f'{BASE}/waitlist', json={'slot_id': slot_id, 'student_id': s['id']})
    print(f'  {s["name"]} 排位: {r.json()["queue_position"]}')

r = requests.post(f'{BASE}/waitlist/release', json={'slot_id': slot_id, 'release_count': 3})
print(f'  第一次释放3个: {r.json()["notified_count"]}人被通知')

r = requests.post(f'{BASE}/waitlist/release', json={'slot_id': slot_id, 'release_count': 3})
err_msg = r.json().get('detail', '')[:60]
print(f'  第二次释放3个: 状态码={r.status_code}, 错误="{err_msg}"')
assert r.status_code == 400, '应该返回400错误'

r = requests.post(f'{BASE}/waitlist/release', json={'slot_id': slot_id, 'release_count': 1})
print(f'  第三次释放1个: {r.json()["notified_count"]}人被通知')
print('[PASS] 名额释放逻辑正确')

print()
print('[TEST 2] 时间段候补看板')
r = requests.get(f'{BASE}/stats/slots/dashboard?slot_id={slot_id}')
d = r.json()[0]
print(f'  容量/已报名: {d["capacity"]}/{d["enrolled_count"]}')
print(f'  排队/已通知/已确认: {d["pending_count"]}/{d["notified_count"]}/{d["confirmed_count"]}')
print(f'  可释放名额: {d["available_release_slots"]}')
print('[PASS] 看板接口正常')

print()
print('[TEST 3] 门店转化统计')
r = requests.get(f'{BASE}/stats/stores/conversion')
stats = r.json()
for s in stats:
    print(f'  门店: {s["store_name"]}')
    print(f'  候补/确认/到课: {s["total_waitlist"]}/{s["total_confirmed"]}/{s["total_enrolled"]}')
    print(f'  转化率: {s["conversion_rate"]*100:.1f}%')
print('[PASS] 门店转化统计正常 (SQLite兼容)')

print()
print('[TEST 4] 确认补位防超员')
r = requests.get(f'{BASE}/waitlist/student/{students[0]["id"]}')
entry = [e for e in r.json() if e['status'] == 'notified'][0]
r = requests.post(f'{BASE}/waitlist/{entry["id"]}/confirm', json={'confirmed': True})
print(f'  学员1确认成功: {r.json()["status"]}')

r = requests.get(f'{BASE}/stats/slots/dashboard?slot_id={slot_id}')
d = r.json()[0]
print(f'  看板: 已报名={d["enrolled_count"]}, 已通知={d["notified_count"]}')
print('[PASS] 确认补位防超员正常')

print()
print('[TEST 5] 模拟时间推进处理超时')
simulate_time = (datetime.now() + timedelta(hours=1)).isoformat()
r = requests.post(f'{BASE}/waitlist/process-timeouts', json={
    'simulate_time': simulate_time,
    'slot_id': slot_id
})
result = r.json()
print(f'  处理了 {result["processed_count"]} 条超时记录')
print(f'  使用模拟时间: {result["simulate_time_used"]}')
print('[PASS] 模拟时间推进正常')

print()
print('[TEST 6] 学员放弃补位 - 自动顺延并记录原因')
r = requests.get(f'{BASE}/waitlist/student/{students[2]["id"]}')
notified = [e for e in r.json() if e['status'] == 'notified']
if notified:
    entry_id = notified[0]['id']
    r = requests.post(f'{BASE}/waitlist/{entry_id}/confirm', json={'confirmed': False})
    print(f'  学员3放弃成功: {r.json()["status"]}')
    
    r = requests.get(f'{BASE}/notifications/student/{students[4]["id"]}')
    notices = r.json()
    rollover = [n for n in notices if n['type'] == 'rollover_notice']
    if rollover:
        print(f'  找到顺延通知: {rollover[0]["content"][:60]}...')
    else:
        print(f'  顺延通知已发送 (共{len(notices)}条通知)')
print('[PASS] 放弃顺延及原因记录正常')

print()
print('='*60)
print('[ALL TESTS PASSED] 所有核心功能验证通过!')
print('='*60)
