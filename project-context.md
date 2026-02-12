# Project Context: Etax System (Advance Transport Co., Ltd.)

## Overview
ระบบสำหรับดึงข้อมูลจากไฟล์รายงานการเติมน้ำมัน (CSV) มาทำการ Lookup กับไฟล์ Master Data หลายไฟล์ เพื่อสร้างไฟล์ข้อมูลที่สมบูรณ์ตาม @TemplateEtax

## Data Mapping Logic
1. **Customer Information:**
   - Source: `รายงานใบเติมน้ำมัน.csv` (รหัสลูกค้า)
   - Step 1: Lookup ใน `@ Mapping Vendor Code.csv` เพื่อหา `AT : Customer Code`
   - Step 2: นำ Code ที่ได้ไป Lookup ใน `@ Customer_Tax ID.xlsx` เพื่อดึง:
     - Name, Address, Tax ID, Branch Name
2. **Company Information (Seller):**
   - Source: `รายงานใบเติมน้ำมัน.csv` (รหัสบริษัท)
   - Step 3: Lookup ใน `@ AT Address.csv` เพื่อดึง:
     - Company Name, Address, Tax ID, Branch
3. **Calculations:**
   - Vat = ยอดรวม * 0.07
   - Net Amount = ยอดรวม + Vat
   - Running Page: รันเลขหน้าอัตโนมัติสำหรับแต่ละกลุ่มใบแจ้งหนี้

## File Path Configuration
- Master Directory: `D:\Project\Etax\Master`
- Input/Output Directory: `D:\Project\Etax`