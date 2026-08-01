import frappe
from rapidocr_pdf import RapidOCRPDF

def extract_pdf_with_rapidocr(file_path: str) -> str:
    """
    Extracts text from a PDF file using RapidOCR.
    Handles both text-based and image-based PDFs.
    """
    try:
        extractor = RapidOCRPDF()
        # The result is typically a list of tuples (page_num, text) or similar.
        # According to rapidocr-pdf docs, extract returns a tuple: (result_list, elapse)
        # where result_list contains elements for each page.
        # Let's inspect the exact return type or assume standard rapidocr format.
        results, elapse = extractor(file_path)
        
        extracted_text = []
        if results:
            for page_idx, page_content in enumerate(results):
                # page_content could be a list of text blocks
                # Usually rapidocr returns a list of [dt_boxes, rec_res, score]
                # Actually, rapidocr_pdf returns string for each page according to some docs,
                # let's be careful and convert to string.
                if isinstance(page_content, list):
                    # For standard rapidocr format: [ [box, text, score], ... ]
                    page_text = "\n".join([item[1] for item in page_content if len(item) > 1 and isinstance(item[1], str)])
                    extracted_text.append(f"--- Page {page_idx + 1} ---\n{page_text}")
                elif isinstance(page_content, str):
                    extracted_text.append(f"--- Page {page_idx + 1} ---\n{page_content}")
                else:
                    extracted_text.append(f"--- Page {page_idx + 1} ---\n{str(page_content)}")
                    
        return "\n\n".join(extracted_text)
    except Exception as e:
        frappe.log_error(f"RapidOCR PDF Extraction failed: {str(e)}", "Local OCR Error")
        return ""
