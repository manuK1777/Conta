import pdfplumber

def extraer_texto_pdf(ruta: str) -> str:
    """
    Extrae texto plano de un PDF (sin OCR).
    """
    with pdfplumber.open(ruta) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)
