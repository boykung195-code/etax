"""
API_AXONS.py - AXONS E-TAX Integration Module
Handles: OAuth2 Auth, PDF Generation, ETDA v2.0 Transformation, and Document Submission.
"""
import requests
import time
import logging
import json
import os
import re
from datetime import datetime, timezone, timedelta
from config import Config

logger = logging.getLogger(__name__)


class AxonsETaxService:
    """Main service class for AXONS E-TAX API integration."""

    def __init__(self):
        self._access_token = None
        self._token_expiry = 0
        self.config = Config

    # =========================================================================
    # 1. AUTH MODULE - OAuth2 Token Management
    # =========================================================================
    def get_access_token(self) -> str:
        """
        Get OAuth2 access token using client_credentials grant.
        Caches token and auto-refreshes when expired.
        """
        # DEBUG: Use manual token provided by user
        manual_token = "qghc4TRv3l6w0r9phn6mMMdz9mIQwK2O"
        logger.warning(f"DEBUG: Using manual token: {manual_token[:5]}...")
        return manual_token
        
        # Return cached token if still valid (with 60s buffer)
        if self._access_token and time.time() < (self._token_expiry - 60):
            return self._access_token

        logger.info("Requesting new OAuth2 access token...")
        try:
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "x-api-key": self.config.GENPDF_API_KEY
            }
            logger.info(f"Requesting OAuth2 token from {self.config.TSP_TOKEN_URL}")
            response = requests.post(
                self.config.TSP_TOKEN_URL,
                data={"grant_type": "client_credentials"},
                auth=(self.config.TSP_CLIENT_ID, self.config.TSP_CLIENT_SECRET),
                headers=headers,
                timeout=30
            )
            
            if response.status_code != 200:
                logger.error(f"Token request failed: {response.status_code} - {response.text}")
                
            response.raise_for_status()
            token_data = response.json()
            logger.debug(f"Raw token response: {json.dumps(token_data)}")

            self._access_token = token_data["access_token"]
            # Default to 3600s if expires_in not provided
            expires_in = token_data.get("expires_in", 3600)
            self._token_expiry = time.time() + expires_in

            logger.info(f"OAuth2 token acquired, expires in {expires_in}s")
            return self._access_token

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to acquire OAuth2 token: {e}")
            raise Exception(f"OAuth2 authentication failed: {e}")

    # =========================================================================
    # 2. PDF SERVICE - Generate PDF via Gen PDF API
    # =========================================================================
    def generate_pdf(self, et_invoice_json: dict) -> str:
        """
        Generate PDF from ET_INVOICE JSON format.
        """
        logger.info("Generating PDF via Gen PDF API...")
        
        # Ensure mandatory fields for QR code and PDF generation
        hdr = et_invoice_json.get("ET_INVOICE_HDR", [{}])[0]
        
        # Pad Tax IDs to 13 digits
        for key in ["COM_TAX_ID", "TAX_ID"]:
            if key in hdr:
                val = str(hdr[key]).strip()
                if val and len(val) < 13:
                    hdr[key] = val.zfill(13)

        if "DOC_TYPE" not in hdr:
            # Map PRINT_FORM_TEMPLATE to DOC_TYPE (01 for INV, 04 for CN, 05 for DN - based on standard)
            # Postman sample showed "01" for Tax Invoice
            template = str(hdr.get("PRINT_FORM_TEMPLATE", "1"))
            doc_type_map = {"1": "01", "2": "04", "3": "05"}
            hdr["DOC_TYPE"] = doc_type_map.get(template, "01")
            
        if "CV_CODE_SAP" not in hdr and "CV_CODE" in hdr:
            hdr["CV_CODE_SAP"] = hdr["CV_CODE"]
            
        if "REFERENCE_NUMBER" not in hdr and "DOC_NUMBER" in hdr:
            hdr["REFERENCE_NUMBER"] = hdr["DOC_NUMBER"]

        try:
            response = requests.post(
                self.config.GENPDF_URL,
                json=et_invoice_json,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": self.config.GENPDF_API_KEY
                },
                timeout=60
            )
            
            if response.status_code != 200:
                logger.error(f"Gen PDF API returned {response.status_code}: {response.text}")
                response.raise_for_status()
                
            result = response.json()

            # Extract Base64 PDF from response
            if isinstance(result, dict):
                pdf_base64 = result.get("pdf") or result.get("data") or result.get("document")
                if pdf_base64:
                    logger.info(f"PDF generated successfully ({len(pdf_base64)} chars)")
                    return pdf_base64

            # If response is directly the base64 string
            if isinstance(result, str):
                logger.info(f"PDF generated successfully ({len(result)} chars)")
                return result

            raise Exception(f"Unexpected Gen PDF response format: {type(result)}")

        except requests.exceptions.RequestException as e:
            # Re-raise with body if available
            body = getattr(e.response, 'text', '') if hasattr(e, 'response') else ''
            logger.error(f"Gen PDF API failed: {e}. Body: {body}")
            raise Exception(f"PDF generation failed: {e}. Body: {body}")

    # =========================================================================
    # 3. DATA TRANSFORMER - ET_INVOICE → ETDA v2.0 (ER3-2560)
    # =========================================================================
    def transform_to_etda(self, et_invoice_json: dict, base64_pdf: str) -> dict:
        """
        Transform ET_INVOICE format to ETDA v2.0 (ER3-2560) format.

        Args:
            et_invoice_json: Dict with ET_INVOICE_HDR and ET_INVOICE_DTL arrays.
            base64_pdf: Base64-encoded PDF string from Gen PDF API.

        Returns:
            ETDA v2.0 formatted dict ready for submission.
        """
        hdr = et_invoice_json["ET_INVOICE_HDR"][0]
        dtl_list = et_invoice_json["ET_INVOICE_DTL"]

        # --- Determine Document Type ---
        template = str(hdr.get("PRINT_FORM_TEMPLATE", "1"))
        type_code, doc_name, endpoint_key = self.config.DOC_TYPE_MAP.get(
            template, ("388", "ใบกำกับภาษี", "taxinvoice")
        )

        # --- Format dates ---
        issue_date = self._format_date_to_iso(hdr.get("DOC_DATE", ""))
        creation_date = datetime.now(timezone(timedelta(hours=7))).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z"
        )

        # --- Seller Tax ID (18 digits: 13-digit tax ID + 5-digit branch) ---
        com_tax_id = str(hdr.get("COM_TAX_ID", self.config.SELLER_TAX_ID)).strip()
        # Ensure leading zero is preserved
        if len(com_tax_id) < 13:
            com_tax_id = com_tax_id.zfill(13)
        seller_branch = self._extract_branch_code(hdr.get("OPERATION_CODE", ""))
        seller_tax_18 = com_tax_id + seller_branch

        # --- Buyer Tax ID (18 digits) ---
        buyer_tax_id = str(hdr.get("TAX_ID", "")).strip()
        if len(buyer_tax_id) < 13:
            buyer_tax_id = buyer_tax_id.zfill(13)
        buyer_branch = str(hdr.get("CV_SEQ", "00000")).strip().zfill(5)
        buyer_tax_18 = buyer_tax_id + buyer_branch

        # --- Amounts (formatted as strings) ---
        nett_amt = self._fmt_amount(hdr.get("NETT_AMT", 0))         # before VAT = line total
        tax_amt = self._fmt_amount(hdr.get("TAX_AMT", 0))
        total_nett = self._fmt_amount(hdr.get("TOTAL_NETT", 0))     # after VAT = grand total
        gross_amt = self._fmt_amount(hdr.get("GROSS_AMT", 0))

        # Determine which is the tax basis and which is grand total
        # GROSS_AMT = NETT_AMT = amount before VAT (tax basis)
        # TOTAL_NETT = amount including VAT (grand total) ... but naming is confusing
        # Looking at sample data: NETT_AMT=2705.7, TAX_AMT=177.01, TOTAL_NETT=2528.69, GROSS_AMT=2705.7
        # So: TOTAL_NETT = before VAT, GROSS_AMT = NETT_AMT = after VAT (grand total)
        # Wait, 2528.69 + 177.01 = 2705.70 ✓
        # So: TOTAL_NETT = base amount (before VAT), NETT_AMT = GROSS_AMT = grand total (after VAT)
        tax_basis = self._fmt_amount(hdr.get("TOTAL_NETT", 0))
        grand_total = self._fmt_amount(hdr.get("NETT_AMT", 0))

        # --- Build ExchangedDocument ---
        doc_number = str(hdr.get("DOC_NUMBER", "")).strip()
        exchanged_document = {
            "ID": doc_number,
            "Name": [doc_name],
            "TypeCode": type_code,
            "IssueDateTime": issue_date,
            "Purpose": None,
            "PurposeCode": None,
            "GlobalID": "2.16.764.1.1.2.1.X.X.X",
            "CreationDateTime": [creation_date],
            "IncludedNote": None
        }

        # For Credit Note / Debit Note, add Purpose/Reference
        if template in ("2", "3"):
            trn_name = str(hdr.get("TRN_NAME", "")).strip()
            exchanged_document["Purpose"] = trn_name if trn_name else None

        # --- Build Seller Trade Party ---
        seller_name = str(hdr.get("COM_NAME_LOCAL", self.config.SELLER_NAME)).strip()
        seller_address_str = str(hdr.get("COM_ADDRESS1", "")).strip()
        s_addr = self._parse_address(seller_address_str)
        
        seller_trade_party = {
            "postalTradeAddress": {
                "PostcodeCode": s_addr["postcode"],
                "BuildingName": "",
                "LineOne": s_addr["line_one"],
                "LineTwo": "",
                "LineThree": None,
                "LineFour": None,
                "LineFive": None,
                "StreetName": None,
                "CityName": "1026",
                "CitySubDivisionName": "102601",
                "CountryID": {
                    "schemeID": "3166-1 alpha-2",
                    "value": "TH"
                },
                "CountrySubDivisionID": "10",  # Default to Bangkok for UAT
                "BuildingNumber": s_addr["building_number"]
            },
            "definedTradeContact": None,
            "id": ["0107566000135"],
            "name": seller_name,
            "SpecifiedTaxRegistration": {
                "ID": {
                    "value": "010554507034500000",
                    "schemeID": "TXID",
                    "schemeName": None,
                    "schemeAgencyID": None,
                    "schemeAgencyName": None,
                    "schemeVersionID": None,
                    "schemeDataURI": None,
                    "schemeURI": None
                }
            }
        }

        # --- Build Buyer Trade Party ---
        buyer_name = str(hdr.get("BILL_NAME", "")).strip()
        buyer_address_str = str(hdr.get("BILL_ADDRESS1", "")).strip()
        b_addr = self._parse_address(buyer_address_str)
        buyer_branch_name = str(hdr.get("CV_SHORT_NAME", "สำนักงานใหญ่")).strip()
        cv_code = str(hdr.get("CV_CODE", "")).strip()

        buyer_trade_party = {
            "ID": [cv_code],
            "Name": buyer_name,
            "PostalTradeAddress": {
                "PostcodeCode": b_addr["postcode"] if b_addr["postcode"] else "10500",
                "BuildingName": None,
                "LineOne": b_addr["line_one"],
                "LineTwo": "",
                "LineThree": None,
                "LineFour": None,
                "LineFive": None,
                "StreetName": None,
                "CityName": "1026",
                "CitySubDivisionName": "102601",
                "CountryID": {
                    "schemeID": "3166-1 alpha-2",
                    "value": "TH"
                },
                "CountrySubDivisionID": "10",
                "BuildingNumber": b_addr["building_number"] or "1"
            },
            "SpecifiedTaxRegistration": {
                "ID": {
                    "value": buyer_tax_18,
                    "schemeID": "TXID",
                    "schemeName": None,
                    "schemeAgencyID": None,
                    "schemeAgencyName": None,
                    "schemeVersionID": None,
                    "schemeDataURI": None,
                    "schemeURI": None
                }
            },
            "DefinedTradeContact": [
                {
                    "TelephoneUniversalCommunication": {
                        "CompleteNumber": ""
                    },
                    "PersonName": buyer_name,
                    "DepartmentName": buyer_branch_name,
                    "EmailURIUniversalCommunication": {
                        "URIID": ""
                    }
                }
            ],
            "GlobalID": None
        }

        # --- Build Referenced Document (for CN/DN) ---
        additional_ref = None
        buyer_order_ref = {
            "IssuerAssignedID": doc_number,
            "ReferenceTypeCode": "ON",
            "IssueDateTime": None
        }

        if template in ("2", "3"):
            ref_doc_no = str(hdr.get("REF_DOC_NUMBER", "")).strip()
            ref_doc_date = self._format_date_to_iso(hdr.get("REF_DOC_DATE", ""))
            if ref_doc_no:
                additional_ref = [{
                    "IssuerAssignedID": ref_doc_no,
                    "ReferenceTypeCode": "ON",
                    "IssueDateTime": ref_doc_date if ref_doc_date else None
                }]

        # --- Build Trade Settlement ---
        trade_settlement = {
            "payerTradeParty": None,
            "payeeTradeParty": None,
            "InvoiceCurrencyCode": {
                "listID": "ISO 4217 3A",
                "value": "THB"
            },
            "ApplicableTradeTax": [
                {
                    "typeCode": "VAT",
                    "CalculatedRate": "7",
                    "BasisAmount": [tax_basis],
                    "CalculatedAmount": [self._fmt_amount(hdr.get("TAX_AMT", 0))]
                }
            ],
            "SpecifiedTradeAllowanceCharge": None,
            "SpecifiedTradePaymentTerms": [
                {
                    "typeCode": None,
                    "dueDateDateTime": None,
                    "description": [None]
                }
            ],
            "SpecifiedTradeSettlementHeaderMonetarySummation": {
                "grandTotalAmount": [{
                    "currencyID": "THB",
                    "currencyCodeListVersionID": None,
                    "value": grand_total
                }],
                "originalInformationAmount": None,
                "lineTotalAmount": [{
                    "currencyID": "THB",
                    "currencyCodeListVersionID": None,
                    "value": tax_basis
                }],
                "differenceInformationAmount": None,
                "allowanceTotalAmount": [{
                    "currencyID": "THB",
                    "currencyCodeListVersionID": None,
                    "value": "0.00"
                }],
                "chargeTotalAmount": [{
                    "currencyID": "THB",
                    "currencyCodeListVersionID": None,
                    "value": "0.00"
                }],
                "taxBasisTotalAmount": [{
                    "currencyID": "THB",
                    "currencyCodeListVersionID": None,
                    "value": tax_basis
                }],
                "taxTotalAmount": [{
                    "currencyID": "THB",
                    "currencyCodeListVersionID": None,
                    "value": self._fmt_amount(hdr.get("TAX_AMT", 0))
                }]
            }
        }

        # --- Build Line Items ---
        line_items = []
        for dtl in dtl_list:
            line_id = str(dtl.get("EXT_NUMBER", 1))
            product_name = str(dtl.get("PRODUCT_NAME", "")).strip()
            qty = self._fmt_amount(dtl.get("COSTPRICE_QTY", 1), decimals=3)
            unit_price = self._fmt_amount(dtl.get("GROSS_PRODUCT", 0))
            line_total = self._fmt_amount(dtl.get("TOTAL_NET_PRODUCT", 0))

            # Calculate line-level tax (proportional)
            total_before_vat = float(hdr.get("TOTAL_NETT", 0) or 0)
            line_total_f = float(dtl.get("TOTAL_NET_PRODUCT", 0) or 0)
            if total_before_vat > 0:
                line_tax = round(line_total_f * float(hdr.get("TAX_AMT", 0) or 0) / total_before_vat, 2)
            else:
                line_tax = 0.0
            line_incl_tax = round(line_total_f + line_tax, 2)

            line_item = {
                "AssociatedDocumentLineDocument": {
                    "LineID": line_id
                },
                "SpecifiedTradeProduct": {
                    "ID": None,
                    "Name": [product_name],
                    "IndividualTradeProductInstance": None,
                    "DesignatedProductClassification": None,
                    "OriginTradeCountry": None,
                    "InformationNote": [
                        {"content": ["0.00"], "subject": "ProductRemark7"},
                        {"content": ["0.00"], "subject": "ProductRemark8"}
                    ],
                    "GlobalID": None,
                    "Description": [product_name]
                },
                "SpecifiedLineTradeAgreement": {
                    "grossPriceProductTradePrice": {
                        "chargeAmount": [{
                            "currencyID": "THB",
                            "currencyCodeListVersionID": None,
                            "value": line_total
                        }],
                        "appliedTradeAllowanceCharge": None
                    }
                },
                "SpecifiedLineTradeDelivery": {
                    "BilledQuantity": {
                        "unitCode": "AU",
                        "unitCodeListID": None,
                        "unitCodeListAgencyID": None,
                        "unitCodeListAgencyName": None,
                        "Value": qty
                    },
                    "PerPackageUnitQuantity": None
                },
                "SpecifiedLineTradeSettlement": {
                    "SpecifiedTradeSettlementLineMonetarySummation": {
                        "netLineTotalAmount": [{
                            "currencyID": "THB",
                            "currencyCodeListVersionID": None,
                            "value": line_total
                        }],
                        "netIncludingTaxesLineTotalAmount": [{
                            "currencyID": "THB",
                            "currencyCodeListVersionID": None,
                            "value": self._fmt_amount(line_incl_tax)
                        }],
                        "taxTotalAmount": [{
                            "currencyID": "THB",
                            "currencyCodeListVersionID": None,
                            "value": self._fmt_amount(line_tax)
                        }]
                    },
                    "ApplicableTradeTax": [
                        {
                            "TypeCode": "VAT",
                            "CalculatedRate": "7",
                            "BasisAmount": [line_total],
                            "CalculatedAmount": [self._fmt_amount(line_tax)]
                        }
                    ],
                    "SpecifiedTradeAllowanceCharge": [
                        {
                            "TypeCode": None,
                            "ActualAmount": ["0.00"],
                            "ChargeIndicator": False,
                            "Reason": None,
                            "ReasonCode": None
                        }
                    ]
                }
            }
            line_items.append(line_item)

        # --- Build LineOA ---
        line_oa = {
            "InternalDocType": "123",
            "CompanyCode": "242",
            "IsReplacement": False,
            "SODocNumber": "12345",
            "RefDocNumber": "12345"
        }

        # --- Assemble Final ETDA v2.0 Document ---
        etda_document = {
            "RequestSendMail": "X",
            "InternalDocNo": "1230572800",
            "Email": "test@gmail.co.th",
            "Branch": "00000",
            "RequestSendSMS": "",
            "MobileNumber": "",
            "RequestSendLineOA": "X",
            "RequestSendSFTP": "X",
            "RequestSendOneBox": "",
            "CCA": {
                "CCACode": "CCACode",
                "CCAName": "CCAName"
            },
            "LineOA": line_oa,
            "ExchangedDocumentContext": {
                "GuidelineSpecifiedDocumentContextParameter": [
                    {
                        "ID": {
                            "schemeAgencyID": "",
                            "schemeVersionID": "v2.0",
                            "value": "ER3-2560"
                        }
                    }
                ]
            },
            "ExchangedDocument": exchanged_document,
            "SupplyChainTradeTransaction": {
                "ApplicableHeaderTradeAgreement": {
                    "SellerTradeParty": seller_trade_party,
                    "BuyerTradeParty": buyer_trade_party,
                    "ApplicableTradeDeliveryTerms": {
                        "DeliveryTypeCode": None
                    },
                    "BuyerOrderReferencedDocument": buyer_order_ref,
                    "AdditionalReferencedDocument": additional_ref
                },
                "ApplicableHeaderTradeDelivery": None,
                "ApplicableHeaderTradeSettlement": trade_settlement,
                "IncludedSupplyChainTradeLineItem": line_items
            },
            "Document": base64_pdf
        }

        return etda_document, endpoint_key

    # =========================================================================
    # 4. SUBMIT SERVICE - Submit Document to Revenue Department
    # =========================================================================
    def submit_document(self, etda_json: dict, doc_type: str) -> dict:
        """
        Submit document to AXONS E-TAX TSP API.

        Args:
            etda_json: ETDA v2.0 formatted document.
            doc_type: One of 'taxinvoice', 'creditnote', 'debitnote'.

        Returns:
            API response as dict.
        """
        token = self.get_access_token()
        url = f"{self.config.TSP_BASE_URL.rstrip('/')}/{self.config.SUBMIT_ENDPOINT.lstrip('/')}"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "x-api-key": self.config.GENPDF_API_KEY
        }
        
        logger.info(f"Submitting {doc_type} to {url}")
        
        # Archive the submitted JSON for review
        try:
            doc_id = etda_json.get("ExchangedDocument", {}).get("ID", f"unknown_{int(datetime.now().timestamp())}")
            archive_path = os.path.join(self.config.SUBMITTED_JSON_DIR, f"{doc_id}_submitted.json")
            if not os.path.exists(self.config.SUBMITTED_JSON_DIR):
                os.makedirs(self.config.SUBMITTED_JSON_DIR)
            with open(archive_path, 'w', encoding='utf-8') as af:
                json.dump(etda_json, af, ensure_ascii=False, indent=2)
            logger.info(f"Archived submission payload to {archive_path}")
        except Exception as ae:
            logger.warning(f"Failed to archive submission payload: {ae}")

        try:
            response = requests.post(
                url,
                json=etda_json,
                headers=headers,
                timeout=60
            )
            
            # For 401, we want to see the response body clearly
            if response.status_code == 401:
                logger.error(f"401 Unauthorized for {doc_type}. Response: {response.text}")
                
            result = response.json()
            logger.info(f"Submit response: status={response.status_code}, body={json.dumps(result, ensure_ascii=False)[:200]}")

            return {
                "http_status": response.status_code,
                "response": result
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"Submit API failed: {e}")
            raise Exception(f"Document submission failed: {e}")

    # =========================================================================
    # 5. STATUS CHECK
    # =========================================================================
    def check_status(self, doc_number: str, doc_date: str, com_tax_id: str,
                     branch: str, internal_doc_no: str, doc_type: str) -> dict:
        """
        Check document submission status.

        Args:
            doc_number: Document number (ExchangedDocument.ID)
            doc_date: ISO 8601 date string
            com_tax_id: Company Tax ID (13 digits)
            branch: Branch code (5 digits)
            internal_doc_no: Internal document number (CV Code)
            doc_type: TypeCode (e.g., "388", "81", "80")

        Returns:
            Status response as dict.
        """
        token = self.get_access_token()
        url = f"{self.config.TSP_BASE_URL}{self.config.STATUS_ENDPOINT}"

        payload = {
            "docNumber": doc_number,
            "docDate": doc_date,
            "comTaxId": com_tax_id,
            "branch": branch,
            "internalDocNo": internal_doc_no,
            "docType": doc_type
        }

        try:
            response = requests.post(
                url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}"
                },
                timeout=30
            )
            return {
                "http_status": response.status_code,
                "response": response.json()
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Status check failed: {e}")
            raise Exception(f"Status check failed: {e}")

    # =========================================================================
    # 6. ORCHESTRATOR - Full Pipeline
    # =========================================================================
    def process_and_submit(self, et_invoice_json: dict) -> dict:
        """
        Complete pipeline: Generate PDF → Transform to ETDA → Submit.

        Args:
            et_invoice_json: Dict with ET_INVOICE_HDR and ET_INVOICE_DTL.

        Returns:
            Result dict with status, doc_number, and submission response.
        """
        doc_number = et_invoice_json["ET_INVOICE_HDR"][0].get("DOC_NUMBER", "unknown")
        logger.info(f"=== Processing document: {doc_number} ===")

        try:
            # Step 1: Generate PDF
            logger.info(f"[{doc_number}] Step 1: Generating PDF...")
            base64_pdf = self.generate_pdf(et_invoice_json)

            # Step 2: Transform to ETDA v2.0
            logger.info(f"[{doc_number}] Step 2: Transforming to ETDA v2.0...")
            etda_json, endpoint_key = self.transform_to_etda(et_invoice_json, base64_pdf)

            # Step 3: Submit
            logger.info(f"[{doc_number}] Step 3: Submitting as {endpoint_key}...")
            submit_result = self.submit_document(etda_json, endpoint_key)

            return {
                "status": "success",
                "doc_number": doc_number,
                "doc_type": endpoint_key,
                "submission": submit_result
            }

        except Exception as e:
            logger.error(f"[{doc_number}] Pipeline failed: {e}")
            return {
                "status": "error",
                "doc_number": doc_number,
                "error": str(e)
            }

    def process_and_submit_batch(self, json_dir: str = None) -> list:
        """
        Batch process all JSON files in a directory.

        Args:
            json_dir: Directory containing ET_INVOICE JSON files.

        Returns:
            List of results for each document.
        """
        if json_dir is None:
            json_dir = self.config.OUTPUT_JSON_DIR

        if not os.path.exists(json_dir):
            raise FileNotFoundError(f"JSON directory not found: {json_dir}")

        results = []
        json_files = sorted([f for f in os.listdir(json_dir) if f.endswith('.json')])
        logger.info(f"Found {len(json_files)} JSON files in {json_dir}")

        for filename in json_files:
            filepath = os.path.join(json_dir, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # JSON files contain an array with one record
                if isinstance(data, list) and len(data) > 0:
                    et_invoice = data[0]
                else:
                    et_invoice = data

                result = self.process_and_submit(et_invoice)
                results.append(result)

            except Exception as e:
                logger.error(f"Failed to process {filename}: {e}")
                results.append({
                    "status": "error",
                    "doc_number": filename,
                    "error": str(e)
                })

        return results

    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    @staticmethod
    def _format_date_to_iso(date_str) -> str:
        """
        Convert date from DDMMYYYY format to ISO 8601 (YYYY-MM-DDT00:00:00.000Z).
        Also handles YYYY-MM-DD, DD/MM/YYYY formats.
        """
        if not date_str or str(date_str).strip() in ("", "nan", "NaT"):
            return ""

        date_str = str(date_str).strip()

        # Already ISO format
        if "T" in date_str:
            return date_str

        try:
            # DDMMYYYY (8 digits, no separator)
            if len(date_str) == 8 and date_str.isdigit():
                dt = datetime.strptime(date_str, "%d%m%Y")
                return dt.strftime("%Y-%m-%dT00:00:00.000Z")

            # YYYY-MM-DD
            if len(date_str) == 10 and date_str[4] == '-':
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                return dt.strftime("%Y-%m-%dT00:00:00.000Z")

            # DD/MM/YYYY
            if len(date_str) == 10 and date_str[2] == '/':
                dt = datetime.strptime(date_str, "%d/%m/%Y")
                return dt.strftime("%Y-%m-%dT00:00:00.000Z")

        except ValueError:
            logger.warning(f"Could not parse date: {date_str}")

        return date_str

    @staticmethod
    def _extract_branch_code(operation_code: str) -> str:
        """
        Extract 5-digit branch code from OPERATION_CODE.
        E.g., 'สาขาที่ 00003' -> '00003', '' -> '00000'
        """
        if not operation_code or str(operation_code).strip() in ("", "nan"):
            return "00000"

        op_str = str(operation_code).strip()

        # Try to find 5 consecutive digits
        import re
        match = re.search(r'(\d{5})', op_str)
        if match:
            return match.group(1)

        # Try to find any digits and pad
        digits = re.findall(r'\d+', op_str)
        if digits:
            return digits[-1].zfill(5)

        return "00000"

    @staticmethod
    def _parse_address(address_str: str) -> dict:
        """
        Heuristic parsing of Thai address strings.
        Extracts Postcode, City (Province), District, etc.
        """
        if not address_str:
            return {
                "postcode": "", "city": "กรุงเทพมหานคร", "district": "",
                "subdistrict": "", "building_number": "", "line_one": ""
            }

        # Postcode: 5 digits
        postcode_match = re.search(r'(\d{5})', address_str)
        postcode = postcode_match.group(1) if postcode_match else ""

        # City (Province): Look for จ. or จังหวัด
        city_match = re.search(r'(?:จ\.|จังหวัด)\s*([^\s]+)', address_str)
        city = city_match.group(1) if city_match else "กรุงเทพมหานคร"

        # District: Look for อ. or อำเภอ or เขต
        district_match = re.search(r'(?:อ\.|อำเภอ|เขต)\s*([^\s]+)', address_str)
        district = district_match.group(1) if district_match else ""

        # Sub-district: Look for ต. or ตำบล or แขวง
        subdistrict_match = re.search(r'(?:ต\.|ตำบล|แขวง)\s*([^\s]+)', address_str)
        subdistrict = subdistrict_match.group(1) if subdistrict_match else ""

        # Building Number: Usually at the start
        # E.g., "61/2 ม.2" -> "61/2"
        building_match = re.match(r'^([\d/]+)', address_str.strip())
        building_number = building_match.group(1) if building_match else "1"

        return {
            "postcode": postcode,
            "city": city,
            "district": district,
            "subdistrict": subdistrict,
            "building_number": building_number,
            "line_one": address_str
        }

    @staticmethod
    def _fmt_amount(value, decimals=2) -> str:
        """Format numeric value as string with specified decimal places."""
        try:
            if value is None or str(value).strip() in ("", "nan"):
                return f"{'0'}.{'0' * decimals}"
            num = float(value)
            return f"{num:.{decimals}f}"
        except (ValueError, TypeError):
            return f"{'0'}.{'0' * decimals}"


# --- Convenience functions for direct usage ---

def generate_pdf(et_invoice_json: dict) -> str:
    """Generate PDF from ET_INVOICE JSON."""
    service = AxonsETaxService()
    return service.generate_pdf(et_invoice_json)


def submit_document(et_invoice_json: dict) -> dict:
    """Full pipeline: generate PDF, transform, and submit."""
    service = AxonsETaxService()
    return service.process_and_submit(et_invoice_json)


def check_status(doc_number: str, doc_date: str, com_tax_id: str,
                 branch: str, internal_doc_no: str, doc_type: str) -> dict:
    """Check document submission status."""
    service = AxonsETaxService()
    return service.check_status(doc_number, doc_date, com_tax_id,
                                branch, internal_doc_no, doc_type)
