import json
import requests
from config import Config

def test_gen_pdf_minimal():
    url = Config.GENPDF_URL
    api_key = Config.GENPDF_API_KEY
    
    # Try with stringified values as in Postman
    payload = {
        "ET_INVOICE_HDR": [
            {
                "COMPANY": "100403",
                "DOC_NUMBER": "TEST001",
                "DOC_DATE": "11022026",
                "DOC_TYPE": "01",
                "PRINT_FORM_TEMPLATE": "1",
                "NETT_AMT": 100.00,
                "TAX_AMT": 7.00,
                "TOTAL_NETT": 107.00,
                "GROSS_AMT": 100.00,
                "TAX_ID": "0105545070345",
                "COM_TAX_ID": "0105519004951",
                "CV_CODE": "1400056",
                "CV_CODE_SAP": "1400056",
                "REFERENCE_NUMBER": "680361000996",
                "BILL_NAME": "Test Customer",
                "COM_NAME_LOCAL": "บริษัท แอ๊ดว้านซ์ทรานสปอร์ต จำกัด",
                "BILL_ADDRESS1": "Test Address",
                "COM_ADDRESS1": "Test Company Address"
            }
        ],
        "ET_INVOICE_DTL": [
            {
                "COMPANY": "100403",
                "DOC_NUMBER": "TEST001",
                "EXT_NUMBER": "1",
                "PRODUCT_NAME": "Test Product",
                "COSTPRICE_QTY": "1.00",
                "GROSS_PRODUCT": "100.00",
                "TOTAL_NET_PRODUCT": "100.00"
            }
        ]
    }
    
    print(f"Testing URL: {url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    try:
        response = requests.post(
            url,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key
            },
            timeout=30
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text[:500]}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_gen_pdf_minimal()
