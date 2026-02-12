import pandas as pd
import os
import re
import json
import logging

# Setup logger
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(levelname)s:%(name)s:%(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

def clean_numeric(val):
    if pd.isna(val) or val == '':
        return 0.0
    if isinstance(val, str):
        val = val.replace(',', '').strip()
    try:
        return float(val)
    except ValueError:
        return 0.0

def format_json_date(date_str):
    """Formats date/datetime to DDMMYYYY for JSON submission."""
    if pd.isna(date_str) or not str(date_str).strip():
        return ""
    clean_date = str(date_str).replace('/', '').replace('-', '').strip()
    try:
        # Case: Already DDMMYYYY
        if len(clean_date) == 8 and clean_date.isdigit():
            day = clean_date[0:2]
            month = clean_date[2:4]
            year = int(clean_date[4:8])
            if year > 2400: year = year - 543
            return f"{day}{month}{year}"
        # Case: Pandas datetime
        dt = pd.to_datetime(date_str, dayfirst=True)
        year = dt.year
        if year > 2400: year = year - 543
        return dt.strftime(f'%d%m{year}')
    except:
        return clean_date

def get_template_name(doc_no):
    """Determines template code from document number suffix."""
    doc_str = str(doc_no).strip()
    if len(doc_str) >= 6:
        code = doc_str[4:6]
        if code == "61": return "1"
        elif code == "64": return "2"
        elif code == "66": return "3"
    return doc_str


def load_csv(path):
    # Support for Excel files
    if path.lower().endswith(('.xls', '.xlsx')):
        try:
            return pd.read_excel(path, dtype=str)
        except Exception as e:
            # Fallback for old excel or other issues if needed
            raise e
            
    try:
        # Load all columns as string by default to preserve leading zeros
        return pd.read_csv(path, encoding='utf-8-sig', dtype=str)
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding='tis-620', dtype=str)

def find_col(df, target_names):
    """Finds a column in df that matches any of the target_names, ignoring case and leading/trailing spaces."""
    if isinstance(target_names, str):
        target_names = [target_names]
    
    # Clean target names
    target_names = [t.strip().lower() for t in target_names]
    
    # Map current columns to cleaned versions
    col_map = {c.strip().lower(): c for c in df.columns}
    
    for target in target_names:
        if target in col_map:
            return col_map[target]
    
    # If not found, try to contain matching
    for target in target_names:
        for c_clean, c_orig in col_map.items():
            if target in c_clean:
                return c_orig
                
    return None

def clean_scientific_notation(val):
    """Converts scientific notation strings (e.g. '6.81181E+11') to full integer strings."""
    if pd.isna(val) or val == '':
        return ''
    s_val = str(val).strip()
    try:
        # Check for scientific notation indicators
        if 'E' in s_val.upper():
            return str(int(float(s_val)))
        # Check for float ending with .0
        if s_val.endswith('.0'):
            return s_val[:-2]
        return s_val
    except:
        return s_val

def format_invoice_date(val):
    """Formats date from YYYY-MM-DD, YYYY/MM/DD, DD/MM/YYYY to DD/MM/YYYY."""
    if pd.isna(val) or val == '':
        return ''
    s_val = str(val).strip()
    
    try:
        # Split time if present
        if ' ' in s_val:
            s_val = s_val.split(' ')[0]
            
        # Case 1: YYYY-MM-DD
        if '-' in s_val:
            parts = s_val.split('-')
            if len(parts) == 3:
                # If specifically 2568-12-01 (Year-Month-Day)
                if len(parts[0]) == 4: 
                    return f"{parts[2]}/{parts[1]}/{parts[0]}"
                # If specifically 01-12-2568 (Day-Month-Year) - Unlikely but possible
                elif len(parts[2]) == 4:
                    return f"{parts[0]}/{parts[1]}/{parts[2]}"

        # Case 2: YYYY/MM/DD or DD/MM/YYYY
        if '/' in s_val:
            parts = s_val.split('/')
            if len(parts) == 3:
                 # If input is already DD/MM/YYYY (e.g. 01/12/2568) -> Return as is
                 if len(parts[2]) == 4:
                     return s_val
                 # If input is YYYY/MM/DD (e.g. 2568/12/01) -> Flip
                 if len(parts[0]) == 4:
                     return f"{parts[2]}/{parts[1]}/{parts[0]}"
                     
        return s_val
    except:
        return s_val

def format_float(val, decimals=2):
    """Formats a value as a float with specified decimal places."""
    if pd.isna(val) or val == '':
        return ''
    try:
        f_val = float(str(val).replace(',', '').strip())
        return "{:.{prec}f}".format(f_val, prec=decimals)
    except:
        return str(val)

def process_etax(transaction_path, master_dir, output_path=None):
    # Load Master Data
    mapping_vendor = load_csv(os.path.join(master_dir, 'Mapping Vendor Code.csv'))
    customer_tax = load_csv(os.path.join(master_dir, 'Customer_Tax ID.csv'))
    at_address = load_csv(os.path.join(master_dir, 'AT Address.csv'))

    # Load Transaction Data
    df = load_csv(transaction_path)

    # Clean headers (strip spaces)
    df.columns = df.columns.str.strip()
    mapping_vendor.columns = mapping_vendor.columns.str.strip()
    customer_tax.columns = customer_tax.columns.str.strip()
    at_address.columns = at_address.columns.str.strip()

    # Identfy critical columns using fuzzy mapping
    col_invoice = find_col(df, 'เลขที่ใบแจ้งหนี้') or 'เลขที่ใบแจ้งหนี้'
    col_product = find_col(df, 'ชื่อสินค้า') or 'ชื่อสินค้า'
    col_license = find_col(df, 'ทะเบียนรถ') or 'ทะเบียนรถ'
    col_customer_id = find_col(df, 'รหัสลูกค้า') or 'รหัสลูกค้า'
    col_company_id = find_col(df, 'รหัสบริษัท') or 'รหัสบริษัท'
    col_amount = find_col(df, 'จำนวนเงิน') or 'จำนวนเงิน'
    col_date = find_col(df, 'วันที่ใบแจ้งหนี้') or 'วันที่ใบแจ้งหนี้'
    col_invoice2 = find_col(df, 'เลขที่ใบแจ้งหนี้2') or 'เลขที่ใบแจ้งหนี้2'
    col_quantity = find_col(df, 'ปริมาณ') or 'ปริมาณ'
    col_price = find_col(df, ['ราคาต่อหน่วย', 'ราคา/หน่วย']) or 'ราคาต่อหน่วย'

    # Clean Scientific Notation for IDs
    if col_invoice in df.columns:
        df[col_invoice] = df[col_invoice].apply(clean_scientific_notation)
    if col_invoice2 in df.columns:
        df[col_invoice2] = df[col_invoice2].apply(clean_scientific_notation)
    if col_customer_id in df.columns:
        df[col_customer_id] = df[col_customer_id].apply(clean_scientific_notation)
    if col_company_id in df.columns:
        df[col_company_id] = df[col_company_id].apply(clean_scientific_notation)

    # Step 1: Customer Lookup Key
    # Ensure keys are clean strings
    df[col_customer_id] = df[col_customer_id].fillna('').astype(str).str.strip()
    mapping_vendor['Vendor'] = mapping_vendor['Vendor'].fillna('').astype(str).str.strip()
    mapping_vendor['AT : Customer Code'] = mapping_vendor['AT : Customer Code'].fillna('').astype(str).str.strip()
    customer_tax['Customer Code'] = customer_tax['Customer Code'].fillna('').astype(str).str.strip()

    # Merge with mapping vendor to get AT : Customer Code if it exists
    df = df.merge(mapping_vendor[['Vendor', 'AT : Customer Code']], 
                  left_on=col_customer_id, right_on='Vendor', how='left')
    
    # Use AT : Customer Code if found, otherwise use original รหัสลูกค้า
    df['lookup_customer_code'] = df['AT : Customer Code'].fillna(df[col_customer_id])

    # Step 2: Merge with Customer Tax ID Data
    # Drop duplicates in customer_tax if any
    customer_tax = customer_tax.drop_duplicates(subset=['Customer Code'])
    df = df.merge(customer_tax, left_on='lookup_customer_code', right_on='Customer Code', how='left')

    # Step 3: Company (Seller) Lookup
    at_address['รหัสบริษัท'] = at_address['รหัสบริษัท'].fillna('').astype(str).str.strip()
    df[col_company_id] = df[col_company_id].fillna('').astype(str).str.strip()
    
    # Handle possible spelling variations in AT Address
    at_address.columns = [c.replace('ภาษ๊', 'ภาษี') for c in at_address.columns]
    at_address = at_address.drop_duplicates(subset=['รหัสบริษัท'])
    
    df = df.merge(at_address, left_on=col_company_id, right_on='รหัสบริษัท', how='left', suffixes=('', '_at'))

    # Calculations
    # User Request: "ยอดขายแล้วถอด Vat7% ออกให้"
    # This means the Input Amount (col_amount) is the Gross Amount (Included VAT)
    
    # Gross Amount (Input)
    df['Net Amount_calc'] = df[col_amount].apply(clean_numeric)
    
    # Calculate VAT: Gross * 7 / 107
    df['VAT_calc'] = (df['Net Amount_calc'] * 7 / 107).round(2)
    
    # Calculate Base Amount: Gross - VAT (Initial per-line)
    df['total_amount_calc'] = (df['Net Amount_calc'] - df['VAT_calc']).round(2)
    
    # --- PRO-RATED VAT ADJUSTMENT LOGIC ---
    # User Request: Calculate VAT from Invoice Total and distribute to items
    
    # 1. Identify the grouping key (Invoice Number)
    invoice_key = col_invoice2 if col_invoice2 in df.columns else col_invoice
    
    # 2. Calculate Expected Invoice Total VAT
    # Group by invoice -> Sum Gross Amount -> Calculate VAT on Sum -> Round
    invoice_totals = df.groupby(invoice_key)['Net Amount_calc'].sum().reset_index()
    invoice_totals['Expected_Invoice_VAT'] = (invoice_totals['Net Amount_calc'] * 7 / 107).round(2)
    
    # 3. Calculate Current Sum of Item VATs
    current_vat_sums = df.groupby(invoice_key)['VAT_calc'].sum().reset_index().rename(columns={'VAT_calc': 'Sum_Item_VAT'})
    
    # 4. Determine Difference (Rounding Error)
    vat_diffs = invoice_totals.merge(current_vat_sums, on=invoice_key)
    vat_diffs['Diff'] = vat_diffs['Expected_Invoice_VAT'] - vat_diffs['Sum_Item_VAT']
    
    # 5. Apply recursive adjustment to items
    # For each invoice with a Diff != 0, add/subtract 0.01 from items until diff is gone
    # To be safe, we adjust the item with the highest value first (usually standard practice)
    
    # We can't vectorized easily this "distribute diff" logic perfectly in pandas without a loop or complex apply
    # Given the scale, a loop over invoices with diffs is acceptable, or a clever sort-and-adjust
    
    # Simplified Vectorized Approach:
    # Add diff to the first item of each invoice group
    # This might put all error on first item, but it ensures Total is correct.
    
    # Filter only diffs that matter (non-zero) roughly
    diff_map = vat_diffs.set_index(invoice_key)['Diff'].to_dict()
    
    def adjust_vat(row):
        inv_id = row[invoice_key]
        if inv_id in diff_map and diff_map[inv_id] != 0:
            adjustment = diff_map[inv_id]
            # Clear the diff from map so we don't apply it again to other items of same invoice
            # Side-effect inside apply is dangerous if parallel, but usually fine in standard pandas
            diff_map[inv_id] = 0 
            return row['VAT_calc'] + adjustment
        return row['VAT_calc']

    # Apply adjustment to the VAT column
    # Note: We need to ensure we only apply it ONCE per invoice. 
    # A cleaner way is to identify the index of the first item for each invoice
    
    first_items_idx = df.drop_duplicates(subset=[invoice_key], keep='first').index
    
    # Add Diff to the VAT of the first item of that invoice
    for idx in first_items_idx:
        inv_id = df.loc[idx, invoice_key]
        if inv_id in diff_map:
            df.loc[idx, 'VAT_calc'] += diff_map[inv_id]
            
    # Recalculate Base Amount after VAT adjustment
    # Base = Gross - Adjusted VAT
    df['total_amount_calc'] = (df['Net Amount_calc'] - df['VAT_calc']).round(2)
    
    # --- END ADJUSTMENT LOGIC ---

    # Page Numbering Logic (Running Page per Invoice)
    # Use col_invoice2 as it's the more "unique" one usually in the template
    group_key = col_invoice2 if col_invoice2 in df.columns else col_invoice
    df['แผ่นที่_calc'] = df.groupby(group_key).cumcount() + 1

    # Concatenated Field: เลขที่ใบแจ้งหนี้_ชื่อสินค้า_ทะเบียนรถ
    df['เลขที่ใบแจ้งหนี้_ชื่อสินค้า_ทะเบียนรถ_calc'] = df[col_invoice].fillna('').astype(str) + "_" + \
                                               df[col_product].fillna('').astype(str) + "_" + \
                                               df[col_license].fillna('').astype(str)

    # Diagnostics
    df['match_status'] = 'Full Match'
    df.loc[df['Name'].isna(), 'match_status'] = 'Customer Missing'
    df.loc[df['ชื่อบริษัท'].isna(), 'match_status'] = 'Seller Missing'
    df.loc[df['Name'].isna() & df['ชื่อบริษัท'].isna(), 'match_status'] = 'Both Missing'

    # Map to Template Columns
    output_df = pd.DataFrame()
    output_df['รหัสลูกค้า'] = df['lookup_customer_code'].astype(str)
    output_df['ชื่อลูกค้า'] = df['Name'].fillna('Missing Master Data')
    
    # Address logic: combine Address 1, Address 2 if Address is empty
    df['full_address'] = df['Address'].fillna('')
    mask = (df['full_address'] == '') | (df['full_address'].isna())
    df.loc[mask, 'full_address'] = df.loc[mask, 'Address 1'].fillna('') + " " + df.loc[mask, 'Address 2'].fillna('')
    
    output_df['ที่อยู่ลูกค้า'] = df['full_address'].fillna('').astype(str)
    output_df['เลขประจำตัวผู้เสียภาษีของลูกค้า'] = df['เลขประจำตัวผู้เสียภาษี'].fillna('').astype(str)
    
    # Branch handling
    # Need to distinguish between Branch Code (e.g. 00000) and Branch Name (e.g. Head Office)
    # df has merged with customer_tax which has 'สาขาที่' (code) and 'ชื่อสาขา' (name)
    
    # Try to find the specific columns from the merge
    # df columns might have _x or _y if conflicts arose
    
    # Find Branch CODE column
    possible_code_cols = ['สาขาที่', 'สาขาที่_x', 'Branch Code'] 
    branch_code_col = next((c for c in possible_code_cols if c in df.columns), None)
    
    # Find Branch NAME column
    possible_name_cols = ['ชื่อสาขา', 'ชื่อสาขา_x', 'Branch Name']
    branch_name_col = next((c for c in possible_name_cols if c in df.columns), None)
    
    output_df['สาขาที่'] = df[branch_code_col].fillna('').astype(str) if branch_code_col else ''
    output_df['ชื่อสาขา'] = df[branch_name_col].fillna('').astype(str) if branch_name_col else ''
    
    output_df['รหัสบริษัท'] = df[col_company_id].astype(str)
    output_df['ชื่อบริษัท'] = df['ชื่อบริษัท'].fillna('').astype(str)
    output_df['ที่อยู่บริษัท'] = df['ที่อยู่_at'].fillna('').astype(str)
    
    # User Request: Add 'ที่อยู่AT' column
    # Since 'ที่อยู่AT' is unique in AT Address.csv and likely not in main df, it won't have a suffix
    # But to be safe check for suffix if logic changes
    at_addr_col = 'ที่อยู่AT' if 'ที่อยู่AT' in df.columns else 'ที่อยู่AT_at'
    if at_addr_col in df.columns:
        output_df['ที่อยู่AT'] = df[at_addr_col].fillna('').astype(str)
    else:
        output_df['ที่อยู่AT'] = ''

    at_tax_col = [c for c in df.columns if 'เลขประจำตัวผู้เสียภาษี' in c and '_at' in c]
    if at_tax_col:
        output_df['เลขประจำตัวผู้เสียภาษีของบริษัท'] = df[at_tax_col[0]].fillna('').astype(str)
    else:
        output_df['เลขประจำตัวผู้เสียภาษีของบริษัท'] = ''
        
    at_branch_col = 'สาขาที่_at' if 'สาขาที่_at' in df.columns else 'สาขาที่_y'
    output_df['ชื่อสาขา_บริษัท'] = df[at_branch_col].fillna('').astype(str)
    
    output_df['วันที่ใบแจ้งหนี้'] = df[col_date].apply(format_invoice_date)
    output_df['เลขที่ใบแจ้งหนี้2'] = df[col_invoice2].astype(str)
    output_df['แผ่นที่'] = df['แผ่นที่_calc'].astype(str)
    output_df['เลขที่ใบแจ้งหนี้_ชื่อสินค้า_ทะเบียนรถ'] = df['เลขที่ใบแจ้งหนี้_ชื่อสินค้า_ทะเบียนรถ_calc']
    output_df['ปริมาณ'] = df[col_quantity].astype(str)
    output_df['ราคาต่อหน่วย'] = df[col_price].apply(lambda x: format_float(x, decimals=3))
    
    output_df['จำนวนเงิน'] = df['total_amount_calc'].apply(format_float)
    output_df['VAT'] = df['VAT_calc'].apply(format_float)
    output_df['จำนวนเงินสุทธิ'] = df['Net Amount_calc'].apply(format_float)
    output_df['สถานะการจับคู่'] = df['match_status']



    if output_path:
        output_df.to_csv(output_path, index=False, encoding='utf-8-sig')
    
    return output_df

def save_to_individual_json(df_result, output_dir):
    """
    Saves a processed DataFrame into individual JSON files (1 per invoice)
    matching the refined structure in convert_etax.py.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

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

    mapping_dtl = {
        "PRODUCT_NAME": "เลขที่ใบแจ้งหนี้_ชื่อสินค้า_ทะเบียนรถ",
        "COSTPRICE_QTY": "ปริมาณ",
        "GROSS_PRODUCT": "ราคาต่อหน่วย",
        "TOTAL_NET_PRODUCT": "จำนวนเงินสุทธิ" 
    }

    # Use DOC_NUMBER as grouping key
    invoice_key = "เลขที่ใบแจ้งหนี้2"
    invoice_buckets = {}

    for _, row in df_result.iterrows():
        raw_doc_no = row.get(invoice_key)
        if pd.isna(raw_doc_no):
            continue
        
        doc_no = str(raw_doc_no).strip().split('.')[0]
        
        if doc_no not in invoice_buckets:
            # Create Header (initialize with base info from first row)
            header_data = {
                "TAX_REGISTER_TYPE": "01",
                "E_TAX_PARTICIPATE": "Y"
            }
            # Initialize numeric sum fields to 0.0
            sum_fields = ["NETT_AMT", "TAX_AMT", "TOTAL_NETT", "GROSS_AMT", "REF_DOC_AMT", "RIGHT_AMT"]
            
            for json_key, excel_col in mapping_hdr.items():
                val = row.get(excel_col, "")
                
                # Apply high-fidelity formatting (13-digit IDs, etc.)
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
                elif json_key in ["DOC_DATE", "REF_DOC_DATE"]:
                    val = format_json_date(val)
                elif json_key == "PRINT_FORM_TEMPLATE":
                    val = get_template_name(val)
                elif json_key == "CV_SEQ":
                    if pd.notna(val):
                        val = str(val).strip().split('.')[0].zfill(5)
                elif json_key in sum_fields:
                    val = 0.0 # Force initialization to zero for accumulation
                
                header_data[json_key] = val
            
            invoice_buckets[doc_no] = {
                "ET_INVOICE_HDR": [header_data],
                "ET_INVOICE_DTL": []
            }

        # Accumulate sums into the existing Header reference
        h = invoice_buckets[doc_no]["ET_INVOICE_HDR"][0]
        sum_fields = ["NETT_AMT", "TAX_AMT", "TOTAL_NETT", "GROSS_AMT", "REF_DOC_AMT", "RIGHT_AMT"]
        for json_key, excel_col in mapping_hdr.items():
            if json_key in sum_fields:
                val = row.get(excel_col, 0)
                try:
                    # Clean the value (handle string formatting, commas, etc.)
                    cleaned_val = str(val).replace(',', '').strip()
                    if cleaned_val == '' or cleaned_val.lower() == 'nan':
                        val_num = 0.0
                    else:
                        val_num = float(cleaned_val)
                    
                    # Add to previous total
                    current_total = h.get(json_key, 0.0)
                    h[json_key] = round(current_total + val_num, 2)
                    
                    # For LARGE documents, only log first few items to avoid log bloat
                    if len(invoice_buckets[doc_no]["ET_INVOICE_DTL"]) < 3:
                        logger.debug(f"DEBUG: Doc {doc_no} Key {json_key} adding {val_num} -> New Total {h[json_key]}")
                except Exception as e:
                    logger.warning(f"Failed to aggregate {json_key} for {doc_no}: {e}")
                    pass

        # Update Detail
        detail_data = {
            "COMPANY": str(row.get("รหัสบริษัท", "")).strip()[:6],
            "DOC_NUMBER": doc_no[:20],
            "EXT_NUMBER": len(invoice_buckets[doc_no]["ET_INVOICE_DTL"]) + 1
        }
        for json_key, excel_col in mapping_dtl.items():
            val = row.get(excel_col, "")
            if json_key in ["COSTPRICE_QTY", "GROSS_PRODUCT", "TOTAL_NET_PRODUCT"]:
                try:
                    val_num = float(str(val).replace(',', '').strip())
                    detail_data[json_key] = round(val_num, 2)
                except:
                    detail_data[json_key] = 0.0
            else:
                detail_data[json_key] = val
            
        invoice_buckets[doc_no]["ET_INVOICE_DTL"].append(detail_data)

    # Save to JSON
    saved_files = []
    for doc_no, data in invoice_buckets.items():
        file_name = f"{doc_no}.json"
        save_path = os.path.join(output_dir, file_name)
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump([data], f, ensure_ascii=False, indent=2)
        saved_files.append(file_name)
    
    return saved_files


if __name__ == "__main__":
    t_path = r'd:\Project\Etax\รายงานใบเติมน้ำมัน.csv'
    m_dir = r'd:\Project\Etax\Master'
    o_path = r'd:\Project\Etax\Processed_Etax.csv'
    
    try:
        result = process_etax(t_path, m_dir, o_path)
        print(f"Successfully processed. Output saved to {o_path}")
        print(result.head())
    except Exception as e:
        print(f"Error: {e}")
