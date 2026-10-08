import pdfplumber
import io
import re

# Minimum characters to be considered a parseable resume
_MIN_RESUME_CHARS = 100

# Common resume section headings for structure detection
_SECTION_KEYWORDS = [
    "education", "experience", "skills", "projects", "certifications",
    "achievements", "summary", "objective", "profile", "internship",
    "publications", "awards", "work experience", "technical skills",
    "co-curricular", "extra-curricular"
]


def _clean_text(text: str) -> str:
    """Remove control characters and normalize whitespace."""
    # Strip null bytes and other control characters except newline/tab
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    # Collapse 3+ consecutive blank lines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Strip trailing spaces from each line
    text = "\n".join(line.rstrip() for line in text.splitlines())
    return text.strip()


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """
    Extract raw text from a PDF resume.

    Raises ValueError for:
    - Corrupt / unreadable PDFs
    - PDFs that yield less than _MIN_RESUME_CHARS of text (scanned images, etc.)
    """
    if not file_bytes:
        raise ValueError("Empty file received.")

    text = ""
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                extracted = page.extract_text(x_tolerance=2, y_tolerance=3)
                if extracted:
                    text += extracted + "\n"
    except Exception as e:
        raise ValueError(f"Could not parse PDF: {str(e)}")

    text = _clean_text(text)

    if len(text) < _MIN_RESUME_CHARS:
        raise ValueError(
            "Extracted text is too short. The PDF may be a scanned image or empty. "
            "Please upload a text-based PDF resume."
        )

    return text


def detect_sections(text: str) -> list[str]:
    """
    Return a list of section headings found in the resume text.
    Used by the ATS engine to check structural completeness.
    """
    found = []
    lower = text.lower()
    for kw in _SECTION_KEYWORDS:
        if kw in lower:
            found.append(kw)
    return found