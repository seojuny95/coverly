from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PyPdfError


def extract_pdf_text(data: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(data))
    except PyPdfError:
        return ""
    return "\n".join(page.extract_text() or "" for page in reader.pages).strip()
