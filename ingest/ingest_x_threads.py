"""
Parse X/Twitter threads via OCR (screenshots) or text into chunks for LanceDB
Uses Apple Vision or tesseract for OCR
"""

def parse_x_thread(file_path: str) -> list[dict]:
    """Parse X thread from screenshot or text."""
    # TODO: Implement X thread parsing with OCR
    pass

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        parse_x_thread(sys.argv[1])
