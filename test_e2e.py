import json
import logging
from API_AXONS import AxonsETaxService

# Setup logging to see what's happening
logging.basicConfig(level=logging.INFO)

def test_e2e_single():
    service = AxonsETaxService()
    
    # Load sample JSON
    filename = 'etax_data/output_json/680361000996.json'
    print(f"Loading sample file: {filename}")
    
    with open(filename, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    # JSON files contain an array with one record
    et_invoice = data[0] if isinstance(data, list) else data
    
    # Run full pipeline
    print("Starting full pipeline...")
    result = service.process_and_submit(et_invoice)
    
    print("\n--- E2E Result ---")
    print(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    test_e2e_single()
