from __future__ import annotations

from docx import Document

from config import (
    GENERAL_SOURCES,
    INDUSTRY_DISPLAY_NAMES,
    INDUSTRY_SOURCES,
    NEWS_TOPICS,
)


def _sources_to_multiline(sources: dict[str, str]) -> str:
    """
    Convert {"Source Name": "@channel"} into multiline text:
    @channel — Source Name
    """
    return "\n".join([f"{channel} — {name}" for name, channel in sources.items()])


def main() -> None:
    doc = Document()

    table = doc.add_table(rows=1, cols=3)
    table.style = "Table Grid"

    hdr = table.rows[0].cells
    hdr[0].text = "Раздел"
    hdr[1].text = "Отрасль / источник"
    hdr[2].text = "Каналы"

    # Industries
    for topic in NEWS_TOPICS:
        display = INDUSTRY_DISPLAY_NAMES.get(topic, topic)
        sources = INDUSTRY_SOURCES.get(topic, {})

        row = table.add_row().cells
        row[0].text = "Отрасль"
        row[1].text = display
        row[2].text = _sources_to_multiline(sources) if sources else "—"

    # General channels (one row)
    row = table.add_row().cells
    row[0].text = "Общие каналы"
    row[1].text = "Если отрасль не выбрана"
    row[2].text = _sources_to_multiline(GENERAL_SOURCES) if GENERAL_SOURCES else "—"

    doc.save(r"c:\Users\Admin\Documents\info_bot\Отрасли_и_каналы.docx")


if __name__ == "__main__":
    main()

