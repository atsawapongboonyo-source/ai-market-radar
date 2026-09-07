AI Market Radar V4.4.1 — Final Decision Context Fix

สาเหตุที่แก้:
- confirmNow() เดิมหยุดเงียบ ๆ เมื่อ JavaScript ตัวแปร context ยังไม่มีค่า
- กรณีแตะ Top Pick แล้วกรอก Webull โดยไม่ได้กด Scan ใน session นั้น ปุ่มจึงดูเหมือนกดไม่ทำงาน

แก้ไข:
- เพิ่ม ensureContext() ให้โหลด /api/scan อัตโนมัติเมื่อ Context ยังไม่มี
- ปุ่ม Final Decision แสดงสถานะ “กำลังตรวจ” แทนการเงียบ
- เพิ่มข้อความ error ที่ชัดเจนหาก Auto Context หรือ /api/auto-confirm มีปัญหา
- คง Signed Premarket, Relative Volume optional และ Final Decision Dashboard เดิมไว้ครบ
- ตรวจ Python syntax และ JavaScript syntax ผ่าน

Commit:
Fix Final Decision context flow in V4.4.1
