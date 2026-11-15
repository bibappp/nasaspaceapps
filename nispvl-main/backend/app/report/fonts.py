"""Шрифты PDF. Встроенные шрифты PDF (Helvetica и др.) не содержат казахских букв
ә ғ қ ң ө ұ ү һ і, поэтому регистрируем DejaVu Sans из backend/app/assets/fonts."""
from __future__ import annotations

from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
FONT_PATH = FONT_DIR / "DejaVuSans.ttf"
FONT_BOLD_PATH = FONT_DIR / "DejaVuSans-Bold.ttf"
FONT = "DejaVuSans"
FONT_BOLD = "DejaVuSans-Bold"

KAZAKH_LETTERS = "әғқңөұүһіӘҒҚҢӨҰҮҺІ"


def register_fonts() -> None:
    if FONT not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT, str(FONT_PATH)))
        pdfmetrics.registerFont(TTFont(FONT_BOLD, str(FONT_BOLD_PATH)))
        pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=FONT_BOLD, italic=FONT, boldItalic=FONT_BOLD)


def missing_glyphs(text: str, font_name: str = FONT) -> set[str]:
    """Символы, для которых в шрифте нет глифа (в PDF они превратились бы в «квадратики»)."""
    register_fonts()
    face = pdfmetrics.getFont(font_name).face
    return {ch for ch in text if not ch.isspace() and ord(ch) not in face.charToGlyph}
