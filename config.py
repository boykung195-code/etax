"""
E-Tax System Configuration
Loads settings from .env file or environment variables.
"""
import os
from dotenv import load_dotenv

# Load .env file from project root
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))


class Config:
    """Centralized configuration for E-Tax API integration."""

    # --- Gen PDF API ---
    GENPDF_URL = os.getenv(
        "GENPDF_URL",
        "https://etaxapi-uat.axonstech.com/api/v1/pdf/generate"
    )
    GENPDF_API_KEY = os.getenv(
        "GENPDF_API_KEY",
        "9d728ad1-5454-4b7e-9fd4-27df4de45e3b"
    )

    # --- AXONS E-TAX TSP Submit API ---
    TSP_BASE_URL = os.getenv(
        "TSP_BASE_URL",
        "https://apigwc-clnp.cpf.co.th/etaxtsp-api-sh-uat"
    )
    TSP_TOKEN_URL = os.getenv(
        "TSP_TOKEN_URL",
        "https://apigwc-clnp.cpf.co.th/etaxtsp-api-sh-uat/oauth2/token"
    )
    TSP_CLIENT_ID = os.getenv(
        "TSP_CLIENT_ID",
        "owKL0l4Uj8ZNrANnb8kADK3p6brqXI7R"
    )
    TSP_CLIENT_SECRET = os.getenv(
        "TSP_CLIENT_SECRET",
        "N8DIHvpNthapVtbyGyu07JPPE3OFxrWv"
    )

    # --- Seller (Company) Info ---
    SELLER_TAX_ID = os.getenv("SELLER_TAX_ID", "0105519004951")
    SELLER_NAME = os.getenv("SELLER_NAME", "บริษัท แอ๊ดว้านซ์ทรานสปอร์ต จำกัด")
    SELLER_BRANCH = os.getenv("SELLER_BRANCH", "00000")

    # --- Submit API Endpoints ---
    SUBMIT_ENDPOINTS = {
        "taxinvoice": "/api/v1/submit/taxinvoice",
        "creditnote": "/api/v1/submit/creditnote",
        "debitnote": "/api/v1/submit/debitnote",
    }
    STATUS_ENDPOINT = "/api/v1/document/status"
    CANCEL_ENDPOINT = "/api/v1/document/cancel"

    # --- Document Type Mapping ---
    # PRINT_FORM_TEMPLATE -> (TypeCode, Name_TH, endpoint_key)
    DOC_TYPE_MAP = {
        "1": ("388", "ใบกำกับภาษี", "taxinvoice"),
        "2": ("81", "ใบลดหนี้", "creditnote"),
        "3": ("80", "ใบเพิ่มหนี้", "debitnote"),
    }

    # --- Paths ---
    BASE_DIR = os.path.dirname(__file__)
    OUTPUT_JSON_DIR = os.path.join(BASE_DIR, "etax_data", "output_json")
    MASTER_DIR = os.path.join(BASE_DIR, "Master")
