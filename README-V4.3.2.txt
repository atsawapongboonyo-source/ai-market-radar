AI Market Radar V4.3.2 — Premarket Route Fix

แก้บั๊ก:
- app.py โหลด scanner.py ตอนเริ่มระบบ เพื่อ register route ของ Scanner ทั้งหมด
- /api/auto-confirm, /api/scan, /api/top-picks และ /api/catalyst/<ticker> อยู่ใน scanner.py ครบ
- คง Signed Premarket Input จาก V4.3.1
- Relative Volume ยังเป็น optional
- อัปเดต health version เป็น 4.3.2

หมายเหตุการตรวจ:
- ตรวจ Python syntax ของ app.py และ scanner.py ผ่าน
- ตรวจ route definitions และ signed Premarket parser แบบ static ผ่าน
- Environment ในเครื่องสร้างไฟล์ไม่มี Flask จึงไม่ได้รัน Flask test client ที่นี่

Commit:
Fix Premarket Gate route in V4.3.2
