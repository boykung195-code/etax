# Developer Instructions

## Development Principles
- **Modularity:** แยกส่วน Data Processing (Python/Pandas) ออกจาก UI Logic
- **Data Validation:** ตรวจสอบความถูกต้องของ Tax ID และ Format วันที่ก่อนประมวลผล
- **Error Handling:** หาก Lookup ไม่เจอข้อมูล Master ให้ระบุสถานะ "Missing Master Data" ใน UI

## Key Roles
- **Data Engineer:** พัฒนาฟังก์ชัน Matching ข้อมูลด้วย Pandas
- **Backend Developer:** พัฒนา API สำหรับรับไฟล์, แปลงเป็น JSON และส่งต่อให้กรมสรรพากร/Email
- **Frontend Developer:** สร้างหน้าจอ Upload และ Dashboard ที่มี UX/UI ทันสมัย (Clean & Minimal)