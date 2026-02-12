import pandas as pd
import json
import os
import glob

def convert_excel_to_etax_json(export_file_path, all_invoices):
    """
    ฟังก์ชันสำหรับอ่านไฟล์ Excel/CSV และประมวลผลข้อมูลลงใน dictionary all_invoices
    """
    try:
        # ตรวจสอบนามสกุลไฟล์เพื่อเลือกวิธีอ่านที่เหมาะสม
        if export_file_path.endswith('.csv'):
            df_export = pd.read_csv(export_file_path, encoding='utf-8-sig')
        else:
            df_export = pd.read_excel(export_file_path)
            
        # กำหนด Mapping ตาม Specification
        # JSON Key (Target) : Excel Header (Source)
        mapping_hdr = {
            "COMPANY": "รหัสบริษัท",
            "OPERATION_CODE": "ชื่อสาขา_บริษัท",
            "COM_TAX_ID": "เลขประจำตัวผู้เสียภาษีของบริษัท", # เลขประจำตัวผู้เสียภาษีของบริษัท
            "DOC_NUMBER": "เลขที่ใบแจ้งหนี้2",
            "DOC_DATE": "วันที่ใบแจ้งหนี้",
            "CV_CODE": "รหัสลูกค้า",        
            "BILL_NAME": "ชื่อลูกค้า",
            "CV_SHORT_NAME": "ชื่อสาขา",   
            "TAX_ID": "เลขประจำตัวผู้เสียภาษีของลูกค้า", 
            "CV_SEQ": "สาขาที่",
            "BILL_ADDRESS1": "ที่อยู่ลูกค้า", 
            "COM_NAME_LOCAL": "ชื่อบริษัท", 
            "COM_ADDRESS1": "ที่อยู่บริษัท",  
            "NETT_AMT": "จำนวนเงินสุทธิ",
            "TAX_AMT": "VAT",
            "NETT_AMT_WITHOUT": "จำนวนเงิน",
            "REMARK_TEXT1": "เลขที่ใบแจ้งหนี้2",
            "PRINT_FORM_TEMPLATE": "เลขที่ใบแจ้งหนี้2" 
        }

        mapping_dtl = {
            "PRODUCT_NAME": "เลขที่ใบแจ้งหนี้_ชื่อสินค้า_ทะเบียนรถ",
            "COSTPRICE_QTY": "ปริมาณ",
            "GROSS_PRODUCT": "ราคาต่อหน่วย",
            "TOTAL_NET_PRODUCT": "จำนวนเงินสุทธิ" 
        }

        def format_date(date_str):
            if pd.isna(date_str) or not str(date_str).strip():
                return ""
            
            clean_date = str(date_str).replace('/', '').replace('-', '').strip()
            
            try:
                if len(clean_date) == 8:
                    day = clean_date[0:2]
                    month = clean_date[2:4]
                    year = int(clean_date[4:8])
                    if year > 2400:
                        year = year - 543
                    return f"{day}{month}{year}"
                
                dt = pd.to_datetime(date_str, dayfirst=True)
                year = dt.year
                if year > 2400:
                    year = year - 543
                return dt.strftime(f'%d%m{year}')
            except:
                return clean_date

        def get_template_name(doc_no):
            """
            ฟังก์ชันตรวจสอบ digit ที่ 5-6 ของเลขที่ใบแจ้งหนี้เพื่อกำหนดรหัส Template (1, 2, 3)
            """
            doc_str = str(doc_no).strip()
            if len(doc_str) >= 6:
                code = doc_str[4:6]
                if code == "61":
                    return "1"  # ใบกำกับภาษี/ใบส่งสินค้า
                elif code == "64":
                    return "2"  # เพิ่มหนี้(ขาย)/ใบกำกับภาษี
                elif code == "66":
                    return "3"  # ลดหนี้(ขาย)/ใบกำกับภาษี
            return doc_str

        # วนลูปประมวลผลข้อมูลในไฟล์
        for _, row in df_export.iterrows():
            raw_doc_no = row.get(mapping_hdr["DOC_NUMBER"])
            if pd.isna(raw_doc_no): continue
            
            doc_no = str(raw_doc_no).strip()
            
            # ดึงค่าตัวเลขเพื่อใช้คำนวณ
            row_net_amt = pd.to_numeric(row.get(mapping_hdr["NETT_AMT"], 0), errors='coerce') or 0
            row_tax_amt = pd.to_numeric(row.get(mapping_hdr["TAX_AMT"], 0), errors='coerce') or 0
            row_net_without = pd.to_numeric(row.get(mapping_hdr["NETT_AMT_WITHOUT"], 0), errors='coerce') or 0
            
            if doc_no not in all_invoices:
                header_data = {
                    "TAX_REGISTER_TYPE": "01",
                    "E_TAX_PARTICIPATE": "Y"
                }
                for json_key, excel_col in mapping_hdr.items():
                    val = row.get(excel_col, "")
                    
                    # จัดการประเภทข้อมูลและความยาวตัวอักษร (Data Type Handling)
                    if json_key == "COMPANY":
                        val = str(val).strip()[:6]
                    elif json_key == "COM_TAX_ID":
                        val = str(val).strip()[:250]
                    elif json_key == "DOC_NUMBER":
                        val = str(val).strip()[:20]
                    elif json_key == "CV_CODE":
                        val = str(val).strip()[:20]
                    elif json_key == "TAX_ID":
                        val = str(val).strip()[:50]
                    elif json_key == "REMARK_TEXT1":
                        val = str(val).strip()[:1024]
                    elif json_key == "DOC_DATE":
                        val = format_date(val)
                    elif json_key == "PRINT_FORM_TEMPLATE":
                        val = get_template_name(val)
                    elif json_key == "CV_SEQ":
                        if pd.notna(val):
                            val = str(val).strip().split('.')[0]
                            val = val.zfill(5)
                    elif json_key in ["NETT_AMT", "TAX_AMT", "NETT_AMT_WITHOUT"]:
                        val = 0 
                        
                    header_data[json_key] = val
                
                all_invoices[doc_no] = {
                    "ET_INVOICE_HDR": [header_data],
                    "ET_INVOICE_DTL": []
                }
            
            # อัปเดตผลรวมสะสมใน Header
            header = all_invoices[doc_no]["ET_INVOICE_HDR"][0]
            header["NETT_AMT"] = round(header["NETT_AMT"] + row_net_amt, 2)
            header["TAX_AMT"] = round(header["TAX_AMT"] + row_tax_amt, 2)
            header["NETT_AMT_WITHOUT"] = round(header["NETT_AMT_WITHOUT"] + row_net_without, 2)

            # สร้างข้อมูล Detail
            detail_data = {
                "COMPANY": str(row.get(mapping_hdr["COMPANY"], "")).strip()[:6],
                "DOC_NUMBER": doc_no[:20],
                "EXT_NUMBER": len(all_invoices[doc_no]["ET_INVOICE_DTL"]) + 1
            }
            for json_key, excel_col in mapping_dtl.items():
                detail_data[json_key] = row.get(excel_col, "")
                
            all_invoices[doc_no]["ET_INVOICE_DTL"].append(detail_data)
            
        print(f"   - Finished processing: {os.path.basename(export_file_path)}")
        
    except Exception as e:
        print(f"   - Error processing {export_file_path}: {e}")

# --- Main execution ---
BASE_DIR = r"D:\Project\Etax\etax_data"
OUTPUT_FILENAME = "etax_all_files_output.json"
output_path = os.path.join(BASE_DIR, OUTPUT_FILENAME)

if __name__ == "__main__":
    print("--- E-Tax Data Conversion Start ---")
    if os.path.exists(BASE_DIR):
        files_to_process = glob.glob(os.path.join(BASE_DIR, "*.csv")) + \
                           glob.glob(os.path.join(BASE_DIR, "*.xlsx"))
        
        if not files_to_process:
            print(f"No Excel or CSV files found in {BASE_DIR}")
        else:
            master_invoices = {}
            for file_path in files_to_process:
                if os.path.basename(file_path) == OUTPUT_FILENAME:
                    continue
                convert_excel_to_etax_json(file_path, master_invoices)
            
            final_json_list = list(master_invoices.values())
            
            try:
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(final_json_list, f, ensure_ascii=False, indent=2)
                print(f"\nSuccessfully combined all files into: {output_path}")
            except Exception as e:
                print(f"Error saving JSON file: {e}")
    else:
        print(f"Error: Path '{BASE_DIR}' does not exist.")