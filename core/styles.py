"""Deck styling constants — template polish later is one-file work."""

FONT_NAME = "Calibri"
TITLE_SIZE_PT = 32
SUBTITLE_SIZE_PT = 16
HEADING_SIZE_PT = 22
BODY_SIZE_PT = 12
TABLE_SIZE_PT = 10
FOOTER_SIZE_PT = 9

DRAFT_FOOTER = "DRAFT — generated locally; review before presenting"
OPP_NAME_TRUNCATE = 40  # pptx tables silently overflow the slide otherwise

ACCENT_RGB = (31, 78, 121)   # dark blue
MUTED_RGB = (89, 89, 89)


def truncate(s: str, limit: int = OPP_NAME_TRUNCATE) -> str:
    return s if len(s) <= limit else s[: limit - 1] + "…"
