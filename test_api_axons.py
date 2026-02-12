import unittest
import json
import os
from API_AXONS import AxonsETaxService

class TestAxonsETaxService(unittest.TestCase):
    def setUp(self):
        self.service = AxonsETaxService()
        self.sample_et_invoice = {
            "ET_INVOICE_HDR": [
                {
                    "TAX_REGISTER_TYPE": "01",
                    "E_TAX_PARTICIPATE": "Y",
                    "COMPANY": "100403",
                    "OPERATION_CODE": "สาขาที่ 00003",
                    "COM_TAX_ID": "0105519004951",
                    "DOC_NUMBER": "680361000996",
                    "DOC_DATE": "16122025",
                    "CV_CODE": "1400056",
                    "BILL_NAME": "บมจ.ซีพีเอฟ (ประเทศไทย)",
                    "CV_SHORT_NAME": "สาขาที่ 00165",
                    "TAX_ID": "107555000023",
                    "CV_SEQ": "00165",
                    "BILL_ADDRESS1": "61/2 หมู่ 2 ถ.สายตรี ต.ธารเกษม อ.พระพุทธบาท จ.สระบุรี 18120",
                    "COM_NAME_LOCAL": "บริษัท แอ๊ดว้านซ์ทรานสปอร์ต จำกัด",
                    "COM_ADDRESS1": "61/2  ม.2  ต.ธารเกษม  อ.พระพุทธบาท  จ.สระบุรี  18120",
                    "NETT_AMT": 2705.7,
                    "TAX_AMT": 177.01,
                    "TOTAL_NETT": 2528.69,
                    "GROSS_AMT": 2705.7,
                    "REMARK_TEXT1": "680361000996",
                    "PRINT_FORM_TEMPLATE": "1",
                    "REF_DOC_NUMBER": "",
                    "REF_DOC_DATE": "",
                    "TRN_NAME": "",
                    "REF_DOC_AMT": 0,
                    "RIGHT_AMT": 0
                }
            ],
            "ET_INVOICE_DTL": [
                {
                    "COMPANY": "100403",
                    "DOC_NUMBER": "680361000996",
                    "EXT_NUMBER": 1,
                    "PRODUCT_NAME": "น้ำมันดีเซล (AT)",
                    "COSTPRICE_QTY": 87.0,
                    "GROSS_PRODUCT": 31.1,
                    "TOTAL_NET_PRODUCT": 2705.7
                }
            ]
        }

    def test_transform_tax_invoice(self):
        """Test transformation of a standard Tax Invoice."""
        etda, endpoint = self.service.transform_to_etda(self.sample_et_invoice, "DUMMY_PDF")
        
        self.assertEqual(endpoint, "taxinvoice")
        self.assertEqual(etda["ExchangedDocument"]["TypeCode"], "388")
        self.assertEqual(etda["ExchangedDocument"]["ID"], "680361000996")
        self.assertEqual(etda["ExchangedDocument"]["IssueDateTime"], "2025-12-16T00:00:00.000Z")
        
        # Test Seller
        self.assertEqual(etda["SupplyChainTradeTransaction"]["ApplicableHeaderTradeAgreement"]["SellerTradeParty"]["name"], "บริษัท แอ๊ดว้านซ์ทรานสปอร์ต จำกัด")
        self.assertEqual(etda["SupplyChainTradeTransaction"]["ApplicableHeaderTradeAgreement"]["SellerTradeParty"]["SpecifiedTaxRegistration"]["ID"]["value"], "010551900495100003")
        
        # Test Buyer
        self.assertEqual(etda["SupplyChainTradeTransaction"]["ApplicableHeaderTradeAgreement"]["BuyerTradeParty"]["Name"], "บมจ.ซีพีเอฟ (ประเทศไทย)")
        self.assertEqual(etda["SupplyChainTradeTransaction"]["ApplicableHeaderTradeAgreement"]["BuyerTradeParty"]["SpecifiedTaxRegistration"]["ID"]["value"], "010755500002300165")
        
        # Test Monies
        monetary_summation = etda["SupplyChainTradeTransaction"]["ApplicableHeaderTradeSettlement"]["SpecifiedTradeSettlementHeaderMonetarySummation"]
        
        self.assertEqual(monetary_summation["taxBasisTotalAmount"][0]["value"], "2528.69")
        self.assertEqual(monetary_summation["taxTotalAmount"][0]["value"], "177.01")
        self.assertEqual(monetary_summation["grandTotalAmount"][0]["value"], "2705.70")
        
        # Test PDF
        self.assertEqual(etda["Document"], "DUMMY_PDF")

    def test_transform_credit_note(self):
        """Test transformation of a Credit Note."""
        import copy
        cn_invoice = copy.deepcopy(self.sample_et_invoice)
        cn_invoice["ET_INVOICE_HDR"][0]["PRINT_FORM_TEMPLATE"] = "2"
        cn_invoice["ET_INVOICE_HDR"][0]["REF_DOC_NUMBER"] = "INV123"
        cn_invoice["ET_INVOICE_HDR"][0]["REF_DOC_DATE"] = "01012025"
        cn_invoice["ET_INVOICE_HDR"][0]["TRN_NAME"] = "Incorrect Price"
        
        etda, endpoint = self.service.transform_to_etda(cn_invoice, "DUMMY_PDF")
        
        self.assertEqual(endpoint, "creditnote")
        self.assertEqual(etda["ExchangedDocument"]["TypeCode"], "81")
        self.assertEqual(etda["ExchangedDocument"]["Purpose"], "Incorrect Price")
        
        additional_ref = etda["SupplyChainTradeTransaction"]["ApplicableHeaderTradeAgreement"]["AdditionalReferencedDocument"][0]
        self.assertEqual(additional_ref["IssuerAssignedID"], "INV123")
        self.assertEqual(additional_ref["IssueDateTime"], "2025-01-01T00:00:00.000Z")

    def test_branch_extraction(self):
        self.assertEqual(self.service._extract_branch_code("สาขาที่ 00003"), "00003")
        self.assertEqual(self.service._extract_branch_code("Head Office"), "00000")
        self.assertEqual(self.service._extract_branch_code("Branch 12"), "00012")
        self.assertEqual(self.service._extract_branch_code(""), "00000")
        self.assertEqual(self.service._extract_branch_code(None), "00000")

    def test_amount_formatting(self):
        self.assertEqual(self.service._fmt_amount(2705.7), "2705.70")
        self.assertEqual(self.service._fmt_amount("2528.69123"), "2528.69")
        self.assertEqual(self.service._fmt_amount(0), "0.00")
        self.assertEqual(self.service._fmt_amount(None), "0.00")
        self.assertEqual(self.service._fmt_amount(10, decimals=3), "10.000")

    def test_date_formatting(self):
        self.assertEqual(self.service._format_date_to_iso("16122025"), "2025-12-16T00:00:00.000Z")
        self.assertEqual(self.service._format_date_to_iso("2025-12-16"), "2025-12-16T00:00:00.000Z")
        self.assertEqual(self.service._format_date_to_iso("16/12/2025"), "2025-12-16T00:00:00.000Z")
        self.assertEqual(self.service._format_date_to_iso(""), "")

if __name__ == '__main__':
    unittest.main()
