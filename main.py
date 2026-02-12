from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import pandas as pd
import io
import os
import json
import logging
import traceback
from processor import process_etax, save_to_individual_json

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MASTER_DIR = r'd:\Project\Etax\Master'
DATA_DIR = r'd:\Project\Etax\etax_data'
OUTPUT_JSON_DIR = os.path.join(DATA_DIR, 'output_json')
UPLOAD_DIR = os.path.join(DATA_DIR, 'uploads')

# Serve Static Files
if not os.path.exists("static"):
    os.makedirs("static")

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def read_index():
    index_path = os.path.join("static", "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return "index.html not found in static directory"

@app.get("/test")
async def test_endpoint():
    logger.info("Test endpoint reached")
    return {"status": "ok"}

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        logger.info(f"--- Processing New Upload: {file.filename} ---")
        content = await file.read()
        
        # Determine extension
        filename = file.filename.lower()
        ext = os.path.splitext(filename)[1]
        if not ext:
            ext = '.csv' # Default fallback
            
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"upload_{timestamp}{ext}"
        archive_path = os.path.join(UPLOAD_DIR, filename)
        
        # Save to archive
        with open(archive_path, "wb") as f:
            f.write(content)
        logger.info(f"Archived uploaded file to {archive_path}")
            
        processed_df = process_etax(archive_path, MASTER_DIR)
        
        # New: Automatically generate individual JSONs for API submission
        saved_jsons = save_to_individual_json(processed_df, OUTPUT_JSON_DIR)
        logger.info(f"Generated {len(saved_jsons)} individual JSON files in {OUTPUT_JSON_DIR}")
            
        first_match = processed_df['สถานะการจับคู่'].iloc[0] if len(processed_df) > 0 else 'EMPTY'
        logger.info(f"Processed {len(processed_df)} rows. Status sample: {first_match}")
        
        data = processed_df.to_dict(orient='records')
        return {
            "status": "success", 
            "data": data,
            "json_count": len(saved_jsons)
        }
    except Exception as e:
        logger.error(f"Error processing upload: {str(e)}")
        logger.error(traceback.format_exc())
        return JSONResponse(status_code=400, content={"status": "error", "message": str(e)})

@app.post("/export")
async def export_json(request: Request):
    try:
        data = await request.json()
        # Dynamic Seller Info based on first row if available
        seller_name = "บริษัท แอ๊ดว้านซ์ทรานสปอร์ต จำกัด"
        seller_tax = "0105519004951"
        
        if len(data) > 0:
            seller_name = data[0].get('ชื่อบริษัท', seller_name)
            seller_tax = data[0].get('เลขประจำตัวผู้เสียภาษีของบริษัท', seller_tax)

        formatted_data = {
            "seller": {
                "taxId": str(seller_tax),
                "name": str(seller_name)
            },
            "invoices": data
        }
        
        file_path = "etax_export.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(formatted_data, f, ensure_ascii=False, indent=4)
            
        return FileResponse(file_path, filename="etax_export.json", media_type="application/json")
    except Exception as e:
        logger.error(f"Error exporting JSON: {str(e)}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.post("/export-csv")
async def export_csv(request: Request):
    try:
        body = await request.json()
        
        # Robustly handle different data structures
        if isinstance(body, dict) and 'data' in body:
            data = body['data']
        elif isinstance(body, list):
            data = body
        else:
            data = body

        logger.info(f"Export CSV requested. Body type: {type(body)}. Rows: {len(data) if isinstance(data, list) else 'N/A'}")
        
        if not data or not isinstance(data, list):
            return JSONResponse(status_code=400, content={"status": "error", "message": "Invalid or empty data format"})
        
        df = pd.DataFrame(data)
        file_path = os.path.join(DATA_DIR, "etax_export.csv")
        df.to_csv(file_path, index=False, encoding='utf-8-sig')
        
        return FileResponse(file_path, filename="etax_export.csv", media_type="text/csv")
    except Exception as e:
        error_msg = f"Error exporting CSV: {str(e)}"
        logger.error(error_msg)
        return JSONResponse(status_code=500, content={"status": "error", "message": error_msg})

@app.post("/export-excel")
async def export_excel(request: Request):
    try:
        body = await request.json()
        if isinstance(body, dict) and 'data' in body:
            data = body['data']
        else:
            data = body

        logger.info(f"Export Excel requested for {len(data) if isinstance(data, list) else 'N/A'} rows")
        
        if not data or not isinstance(data, list):
            return JSONResponse(status_code=400, content={"status": "error", "message": "Invalid or empty data format"})
        
        df = pd.DataFrame(data)
        file_path = os.path.join(DATA_DIR, "etax_export.xlsx")
        
        # Save as Excel using openpyxl engine
        df.to_excel(file_path, index=False, engine='openpyxl')
        logger.info(f"Excel saved to {file_path}")
        
        return FileResponse(
            file_path, 
            filename="etax_export.xlsx", 
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        error_msg = f"Error exporting Excel: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        return JSONResponse(status_code=500, content={"status": "error", "message": error_msg})

@app.get("/master-status")
async def get_master_status():
    files = ["Mapping Vendor Code.csv", "Customer_Tax ID.csv", "AT Address.csv"]
    status = {}
    for f in files:
        path = os.path.join(MASTER_DIR, f)
        status[f] = os.path.exists(path)
    return status

# =============================================================================
# AXONS E-TAX API Endpoints
# =============================================================================
from API_AXONS import AxonsETaxService

etax_service = AxonsETaxService()

@app.post("/api/generate-pdf")
async def api_generate_pdf(request: Request):
    """Generate PDF from ET_INVOICE JSON."""
    try:
        data = await request.json()
        # Support both direct ET_INVOICE and array-wrapped format
        if isinstance(data, list) and len(data) > 0:
            et_invoice = data[0]
        else:
            et_invoice = data

        base64_pdf = etax_service.generate_pdf(et_invoice)
        doc_number = et_invoice.get("ET_INVOICE_HDR", [{}])[0].get("DOC_NUMBER", "unknown")

        return {
            "status": "success",
            "doc_number": doc_number,
            "pdf_base64": base64_pdf,
            "pdf_length": len(base64_pdf)
        }
    except Exception as e:
        logger.error(f"Generate PDF error: {e}")
        logger.error(traceback.format_exc())
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.post("/api/submit")
async def api_submit(request: Request):
    """Full pipeline: Generate PDF → Transform to ETDA v2.0 → Submit."""
    try:
        data = await request.json()
        if isinstance(data, list) and len(data) > 0:
            et_invoice = data[0]
        else:
            et_invoice = data

        result = etax_service.process_and_submit(et_invoice)
        status_code = 200 if result["status"] == "success" else 500
        return JSONResponse(status_code=status_code, content=result)
    except Exception as e:
        logger.error(f"Submit error: {e}")
        logger.error(traceback.format_exc())
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.post("/api/check-status")
async def api_check_status(request: Request):
    """Check document submission status."""
    try:
        data = await request.json()
        result = etax_service.check_status(
            doc_number=data.get("docNumber", ""),
            doc_date=data.get("docDate", ""),
            com_tax_id=data.get("comTaxId", ""),
            branch=data.get("branch", "00000"),
            internal_doc_no=data.get("internalDocNo", ""),
            doc_type=data.get("docType", "388")
        )
        return result
    except Exception as e:
        logger.error(f"Check status error: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.post("/api/submit-batch")
async def api_submit_batch(request: Request):
    """Batch submit all JSON files from output_json directory."""
    try:
        body = await request.json()
        json_dir = body.get("json_dir", None)
        
        # Run blocking batch submission in a separate thread to keep server responsive
        import anyio
        results = await anyio.to_thread.run_sync(etax_service.process_and_submit_batch, json_dir)

        success_count = sum(1 for r in results if r.get("status") == "success")
        error_count = sum(1 for r in results if r.get("status") == "error")

        return {
            "status": "completed",
            "total": len(results),
            "success": success_count,
            "errors": error_count,
            "results": results
        }
    except Exception as e:
        logger.error(f"Batch submit error: {e}")
        logger.error(traceback.format_exc())
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.post("/api/transform-preview")
async def api_transform_preview(request: Request):
    """Preview ETDA v2.0 transformation without submitting (for debugging)."""
    try:
        data = await request.json()
        if isinstance(data, list) and len(data) > 0:
            et_invoice = data[0]
        else:
            et_invoice = data

        # Transform with a dummy PDF placeholder
        etda_json, endpoint_key = etax_service.transform_to_etda(
            et_invoice, "<<PLACEHOLDER_BASE64_PDF>>"
        )

        return {
            "status": "success",
            "endpoint_key": endpoint_key,
            "etda_preview": etda_json
        }
    except Exception as e:
        logger.error(f"Transform preview error: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
