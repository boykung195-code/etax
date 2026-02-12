import pandas as pd
import json
import os
import glob

def clean_numeric(val):
    """จัดการตัวเลข: ถ้าเป็น NaN หรือ 0 ให้ส่ง 0 (int), ถ้ามีค่าให้ส่ง float 2 ตำแหน่ง"""
    num = pd.to_numeric(val, errors='coerce')
    if pd.isna(num) or num == 0:
        return 0
    return round(float(num), 2)

def format_date(date_str):
    if pd.isna(date_str) or not str(date_str).strip():
        return ""
    clean_date = str(date_str).replace('/', '').replace('-', '').strip()
    try:
        # กรณีมาเป็น DDMMYYYY ตรงๆ
        if len(clean_date) == 8 and clean_date.isdigit():
            day = clean_date[0:2]
            month = clean_date[2:4]
            year = int(clean_date[4:8])
            if year > 2400: year = year - 543
            return f"{day}{month}{year}"
        # กรณีใช้ pandas parse
        dt = pd.to_datetime(date_str, dayfirst=True)
        year = dt.year
        if year > 2400: year = year - 543
        return dt.strftime(f'%d%m{year}')
    except:
        return clean_date

def get_template_name(doc_no):
    doc_str = str(doc_no).strip()
    if len(doc_str) >= 6:
        code = doc_str[4:6]
        if code == "61": return "1"
        elif code == "64": return "2"
        elif code == "66": return "3"
    return doc_str

def convert_excel_to_individual_json(export_file_path, output_dir):
    """
    อ่านไฟล์ Excel/CSV และบันทึกเป็น JSON แยกตามเลขที่ใบแจ้งหนี้
    """
    try:
        mapping_hdr = {
            "COMPANY": "รหัสบริษัท",
            "OPERATION_CODE": "ชื่อสาขา_บริษัท",
            "COM_TAX_ID": "เลขประจำตัวผู้เสียภาษีของบริษัท",
            "DOC_NUMBER": "เลขที่ใบแจ้งหนี้2",
            "DOC_DATE": "วันที่ใบแจ้งหนี้",
            "CV_CODE": "รหัสลูกค้า",        
            "BILL_NAME": "ชื่อลูกค้า",
            "CV_SHORT_NAME": "ชื่อสาขา",   
            "TAX_ID": "เลขประจำตัวผู้เสียภาษีของลูกค้า", 
            "CV_SEQ": "สาขาที่",
            "BILL_ADDRESS1": "ที่อยู่ลูกค้า", 
            "COM_NAME_LOCAL": "ชื่อบริษัท", 
            "COM_NAME_LOCAL": "ชื่อบริษัท", 
            "COM_ADDRESS1": "ที่อยู่บริษัท",  
            "NETT_AMT": "จำนวนเงินสุทธิ",
            "TAX_AMT": "VAT",
            "TOTAL_NETT": "จำนวนเงิน",
            "GROSS_AMT": "จำนวนเงินสุทธิ",
            "REMARK_TEXT1": "เลขที่ใบแจ้งหนี้2",
            "PRINT_FORM_TEMPLATE": "เลขที่ใบแจ้งหนี้2",
            "REF_DOC_NUMBER": "อ้างอิงใบกำกับภาษีเลขที่",
            "REF_DOC_DATE": "วันที่เอกสารอ้างอิง",
            "TRN_NAME": "สาเหตุ",
            "REF_DOC_AMT": "มูลค่าตามใบกำกับภาษีเดิม",
            "RIGHT_AMT": "มูลค่าที่ถูกต้อง"
        }

        if export_file_path.endswith('.csv'):
            df_export = pd.read_csv(export_file_path, encoding='utf-8-sig')
        else:
            # กำหนด dtype เพื่อป้องกันไม่ให้ pandas ตัดเลข 0 ข้างหน้า
            df_export = pd.read_excel(export_file_path, dtype={
                mapping_hdr["COM_TAX_ID"]: str,
                mapping_hdr["TAX_ID"]: str,
                mapping_hdr["CV_SEQ"]: str
            })

        mapping_dtl = {
            "PRODUCT_NAME": "เลขที่ใบแจ้งหนี้_ชื่อสินค้า_ทะเบียนรถ",
            "COSTPRICE_QTY": "ปริมาณ",
            "GROSS_PRODUCT": "ราคาต่อหน่วย",
            "TOTAL_NET_PRODUCT": "จำนวนเงินสุทธิ" 
        }

        # รวบรวมข้อมูลแยกตามเลขที่ใบแจ้งหนี้ก่อนบันทึก
        invoice_buckets = {}

        for _, row in df_export.iterrows():
            raw_doc_no = row.get(mapping_hdr["DOC_NUMBER"])
            if pd.isna(raw_doc_no): continue
            
            doc_no = str(raw_doc_no).strip()
            
            row_net_amt = pd.to_numeric(row.get(mapping_hdr["NETT_AMT"], 0), errors='coerce') or 0
            row_tax_amt = pd.to_numeric(row.get(mapping_hdr["TAX_AMT"], 0), errors='coerce') or 0
            row_total_nett = pd.to_numeric(row.get(mapping_hdr["TOTAL_NETT"], 0), errors='coerce') or 0
            row_gross_amt = pd.to_numeric(row.get(mapping_hdr["GROSS_AMT"], 0), errors='coerce') or 0
            
            if doc_no not in invoice_buckets:
                header_data = {
                    "TAX_REGISTER_TYPE": "01",
                    "E_TAX_PARTICIPATE": "Y"
                }
                for json_key, excel_col in mapping_hdr.items():
                    val = row.get(excel_col, "")
                    
                    if json_key == "COMPANY": val = str(val).strip()[:6]
                    elif json_key == "COM_TAX_ID": 
                        if pd.notna(val):
                            val = str(val).strip().split('.')[0].zfill(13)[:13]
                        else:
                            val = ""
                    elif json_key == "DOC_NUMBER": val = str(val).strip()[:20]
                    elif json_key == "CV_CODE": val = str(val).strip()[:20]
                    elif json_key == "TAX_ID": 
                        if pd.notna(val):
                            val = str(val).strip().split('.')[0].zfill(13)[:13]
                        else:
                            val = ""
                    elif json_key == "REMARK_TEXT1": val = str(val).strip()[:1024]
                    elif json_key == "REF_DOC_NUMBER": val = str(val).strip()[:20]
                    elif json_key == "TRN_NAME": val = str(val).strip()[:250]
                    elif json_key in ["DOC_DATE", "REF_DOC_DATE"]:
                        val = format_date(val)
                        if json_key == "REF_DOC_DATE": val = val[:10]
                    elif json_key == "PRINT_FORM_TEMPLATE":
                        val = get_template_name(val)
                    elif json_key == "CV_SEQ":
                        if pd.notna(val):
                            val = str(val).strip().split('.')[0].zfill(5)
                    elif json_key in ["NETT_AMT", "TAX_AMT", "TOTAL_NETT", "GROSS_AMT", "REF_DOC_AMT", "RIGHT_AMT"]:
                        val = clean_numeric(val)
                        if json_key in ["NETT_AMT", "TAX_AMT", "TOTAL_NETT", "GROSS_AMT"]:
                            val = 0 # ตั้งต้นเพื่อสะสม
                        
                    header_data[json_key] = val
                
                invoice_buckets[doc_no] = {
                    "ET_INVOICE_HDR": [header_data],
                    "ET_INVOICE_DTL": []
                }
            
            # อัปเดตผลรวมสะสม
            header = invoice_buckets[doc_no]["ET_INVOICE_HDR"][0]
            header["NETT_AMT"] = clean_numeric(header["NETT_AMT"] + row_net_amt)
            header["TAX_AMT"] = clean_numeric(header["TAX_AMT"] + row_tax_amt)
            header["TOTAL_NETT"] = clean_numeric(header["TOTAL_NETT"] + row_total_nett)
            header["GROSS_AMT"] = clean_numeric(header["GROSS_AMT"] + row_gross_amt)

            # สร้างข้อมูล Detail
            detail_data = {
                "COMPANY": str(row.get(mapping_hdr["COMPANY"], "")).strip()[:6],
                "DOC_NUMBER": doc_no[:20],
                "EXT_NUMBER": len(invoice_buckets[doc_no]["ET_INVOICE_DTL"]) + 1
            }
            for json_key, excel_col in mapping_dtl.items():
                val = row.get(excel_col, "")
                if json_key in ["COSTPRICE_QTY", "GROSS_PRODUCT", "TOTAL_NET_PRODUCT"]:
                    detail_data[json_key] = clean_numeric(val)
                else:
                    detail_data[json_key] = val
                
            invoice_buckets[doc_no]["ET_INVOICE_DTL"].append(detail_data)

        # บันทึกไฟล์แยกตาม doc_no
        for doc_no, data in invoice_buckets.items():
            file_name = f"{doc_no}.json"
            save_path = os.path.join(output_dir, file_name)
            # โครงสร้าง JSON เป็น Array ตามข้อกำหนดเดิมแต่มีแค่ 1 record ต่อไฟล์
            final_output = [data] 
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(final_output, f, ensure_ascii=False, indent=2)
            print(f"      - Saved: {file_name}")

    except Exception as e:
        print(f"   - Error processing {export_file_path}: {e}")

# --- ส่วนรันโปรแกรม ---
BASE_DIR = r"D:\Project\Etax\etax_data"
# สร้างโฟลเดอร์สำหรับเก็บผลลัพธ์แยกต่างหากเพื่อไม่ให้ปนกับไฟล์ต้นทาง
RESULT_DIR = os.path.join(BASE_DIR, "output_json")

if __name__ == "__main__":
    print("--- E-Tax Individual File Conversion Start ---")
    
    if not os.path.exists(RESULT_DIR):
        os.makedirs(RESULT_DIR)
        print(f"Created output directory: {RESULT_DIR}")

    if os.path.exists(BASE_DIR):
        files_to_process = glob.glob(os.path.join(BASE_DIR, "*.csv")) + \
                           glob.glob(os.path.join(BASE_DIR, "*.xlsx"))
        
        if not files_to_process:
            print(f"No Excel or CSV files found in {BASE_DIR}")
        else:
            for file_path in files_to_process:
                # ข้ามไฟล์ผลลัพธ์เก่าถ้ามี
                if "output" in file_path.lower(): continue
                
                print(f"Processing: {os.path.basename(file_path)}")
                convert_excel_to_individual_json(file_path, RESULT_DIR)
            
            print(f"\nAll files processed. JSON files are located in: {RESULT_DIR}")
    else:
        print(f"Error: Path '{BASE_DIR}' does not exist.")