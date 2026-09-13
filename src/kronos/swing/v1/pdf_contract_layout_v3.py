"""Versioned, measured layout only; all contract characters remain intact."""
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import Preformatted

RENDERER_IDENTITY = "SWING-V3-ANSWER-CONTRACT-RENDERER"
RENDERER_VERSION = "1.1.0"
PAGE_MARGIN = 54.0
FRAME_PADDING = 6.0
USABLE_WIDTH = A4[0] - 2 * (PAGE_MARGIN + FRAME_PADDING)
FONT_SIZE = 7.5
LINE_HEIGHT = 10.0
PARAGRAPH_SPACING = 6.0
BLOCK_SPACING = 8.0
MINIMUM_PAGE_REMAINDER = LINE_HEIGHT


def measured_lines(text: str, width: float = USABLE_WIDTH) -> tuple[str, ...]:
    """Insert line boundaries only, without deleting spaces or splitting glyphs.

    Long unbroken identities use the same measured character rule. No hyphen,
    ellipsis, continuation marker or other character enters contract values.
    """
    if width < stringWidth("M", "Courier", FONT_SIZE):
        raise ValueError("VISUAL_V3_CONTRACT_WIDTH_INVALID")
    result = []
    for original in text.split("\n"):
        if not original:
            result.append("")
        while original:
            low, high = 1, len(original)
            while low < high:
                mid = (low + high + 1) // 2
                if stringWidth(original[:mid], "Courier", FONT_SIZE) <= width:
                    low = mid
                else:
                    high = mid - 1
            count = low
            # Prefer a word boundary while preserving its literal space.
            if count < len(original):
                space = original.rfind(" ", 0, count)
                if space >= count // 2:
                    count = space + 1
            result.append(original[:count])
            original = original[count:]
    return tuple(result)


def contract_block(text: str) -> Preformatted:
    style = ParagraphStyle(
        "V3BoundedContract", fontName="Courier", fontSize=FONT_SIZE,
        leading=LINE_HEIGHT, leftIndent=0, rightIndent=0,
        spaceBefore=0, spaceAfter=BLOCK_SPACING,
    )
    block = Preformatted("", style)
    block.lines = list(measured_lines(text))
    # Preformatted.split carries whole measured lines to the next page; it
    # emits nothing when less than one LINE_HEIGHT remains in the frame.
    return block
