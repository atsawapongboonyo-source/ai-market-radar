AI Market Radar V4.3 — Premarket Gate Lite

เพิ่ม/แก้จาก V4.2:
- ราคาปัจจุบันจาก Webull: ยังจำเป็นสำหรับ Final Decision
- % Premarket: ยังจำเป็นก่อนให้สถานะ CONFIRMED
- Relative Volume: เปลี่ยนเป็น OPTIONAL ไม่บังคับกรอก
- ถ้าไม่กรอก Relative Volume ระบบจะถือเป็น Neutral และไม่หักคะแนน
- ถ้ากรอก Relative Volume ระบบยังใช้ช่วยยืนยัน Momentum:
  * 1.2x–3.0x = เพิ่มน้ำหนักเชิงบวก
  * >3.0x = Momentum สูงมาก แต่เตือนความผันผวน
  * <0.8x = ลดคะแนนเล็กน้อย
- Premarket > +6% = DONT_CHASE / ไม่ไล่ราคา
- Premarket < -5% = BLOCK การเข้าใหม่จนกว่าจะฟื้น
- ระบบ Scanner / Recovery / Cache / Catalyst / Top Pick / Confidence Calibration / Final Decision ยังอยู่ครบ

เหตุผล:
Webull บางหน้าหรือบางช่วงเวลาไม่ได้แสดง Relative Volume ชัดเจน จึงไม่ควรทำให้ผู้ใช้ติด Gate เพียงเพราะไม่มีค่านี้

Commit แนะนำ:
Upgrade AI Market Radar to V4.3 Premarket Gate Lite
