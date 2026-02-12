from processor import process_etax
import json

t_path = r'd:\Project\Etax\รายงานใบเติมน้ำมัน.csv'
m_dir = r'd:\Project\Etax\Master'

try:
    df = process_etax(t_path, m_dir)
    # Check first row
    first_row = df.iloc[0].to_dict()
    print("--- FIRST ROW PREVIEW ---")
    for k, v in first_row.items():
        print(f"{k}: {v}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
