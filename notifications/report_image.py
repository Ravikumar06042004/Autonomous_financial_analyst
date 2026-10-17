from datetime import datetime
from pathlib import Path
import textwrap

from PIL import Image, ImageDraw, ImageFont


BASE_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = BASE_DIR / "data" / "telegram_reports"

IMAGE_WIDTH = 1400
PADDING = 60
HEADER_HEIGHT = 160
MAX_BODY_HEIGHT = 1650


def load_font(size, bold=False, mono=False):
    """Load Windows fonts with fallback support."""
    if mono:
        candidates = [
            r"C:\Windows\Fonts\consola.ttf",
            r"C:\Windows\Fonts\cour.ttf",
        ]
    elif bold:
        candidates = [
            r"C:\Windows\Fonts\segoeuib.ttf",
            r"C:\Windows\Fonts\arialbd.ttf",
        ]
    else:
        candidates = [
            r"C:\Windows\Fonts\segoeui.ttf",
            r"C:\Windows\Fonts\arial.ttf",
        ]

    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size)

    return ImageFont.load_default()


def _split_table_row(line):
    """Split one Markdown pipe-table row into cells."""
    return [
        cell.strip()
        for cell in line.strip().strip("|").split("|")
    ]


def _is_table_separator(line):
    """Recognize Markdown table separator rows."""
    cells = _split_table_row(line)

    return bool(cells) and all(
        bool(cell) and all(char in "-: " for char in cell)
        for cell in cells
    )


def _format_table_rows(rows):
    """Convert Markdown table rows into clean aligned text rows."""
    if not rows:
        return []

    column_count = max(len(row) for row in rows)
    padded = [
        row + [""] * (column_count - len(row))
        for row in rows
    ]

    widths = []

    for column in range(column_count):
        width = max(
            len(row[column])
            for row in padded
        )
        widths.append(min(max(width, 8), 24))

    formatted = []

    for row_index, row in enumerate(padded):
        cells = []

        for column, cell in enumerate(row):
            width = widths[column]

            if len(cell) > width:
                cell = cell[:width - 1] + "…"

            cells.append(cell.ljust(width))

        formatted.append({
            "kind": "table_header" if row_index == 0 else "table_row",
            "text": "  ".join(cells).rstrip(),
        })

    return formatted


def _parse_report(report_text):
    """Convert Markdown report text into renderable content blocks."""
    source_lines = str(report_text).splitlines()
    blocks = []
    index = 0

    while index < len(source_lines):
        line = source_lines[index].strip()

        if not line:
            blocks.append({"kind": "blank", "text": ""})
            index += 1
            continue

        # Detect a Markdown table from its header + separator.
        if (
            "|" in line
            and index + 1 < len(source_lines)
            and _is_table_separator(source_lines[index + 1])
        ):
            rows = [_split_table_row(line)]
            index += 2

            while index < len(source_lines):
                candidate = source_lines[index].strip()

                if not candidate or "|" not in candidate:
                    break

                if not _is_table_separator(candidate):
                    rows.append(_split_table_row(candidate))

                index += 1

            blocks.extend(_format_table_rows(rows))
            continue

        if line.startswith("## "):
            blocks.append({
                "kind": "heading",
                "text": line[3:].strip(),
            })

        elif line.startswith("# "):
            blocks.append({
                "kind": "title",
                "text": line[2:].strip(),
            })

        elif line.startswith("- ") or line.startswith("* "):
            blocks.append({
                "kind": "bullet",
                "text": "• " + line[2:].strip(),
            })

        else:
            blocks.append({
                "kind": "body",
                "text": line,
            })

        index += 1

    return blocks or [{
        "kind": "body",
        "text": "No report content was generated.",
    }]


def _wrap_block(block, fonts, max_width):
    """Wrap text according to its actual drawing font."""
    text = block["text"]

    if not text:
        return [block]

    font = fonts.get(block["kind"], fonts["body"])
    words = text.split()
    lines = []
    current = ""

    for word in words:
        candidate = f"{current} {word}".strip()

        if current and font.getlength(candidate) > max_width:
            lines.append({
                "kind": block["kind"],
                "text": current,
            })
            current = word
        else:
            current = candidate

    if current:
        lines.append({
            "kind": block["kind"],
            "text": current,
        })

    return lines or [block]


def _line_height(kind):
    return {
        "title": 44,
        "heading": 40,
        "table_header": 34,
        "table_row": 32,
        "bullet": 32,
        "body": 33,
        "blank": 17,
    }.get(kind, 33)


def _paginate(blocks, fonts):
    """Split content into pages without clipping the bottom."""
    max_width = IMAGE_WIDTH - (PADDING * 2)
    expanded = []

    for block in blocks:
        expanded.extend(
            _wrap_block(block, fonts, max_width)
        )

    pages = []
    current_page = []
    used_height = 0

    for block in expanded:
        height = _line_height(block["kind"])

        if (
            current_page
            and used_height + height > MAX_BODY_HEIGHT
        ):
            pages.append(current_page)
            current_page = []
            used_height = 0

        current_page.append(block)
        used_height += height

    if current_page:
        pages.append(current_page)

    return pages or [[{
        "kind": "body",
        "text": "No report content was generated.",
    }]]


def render_report_images(report_text):
    """Render clean, multi-page market report images."""
    if not str(report_text).strip():
        raise ValueError("The market report is empty.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    title_font = load_font(30, bold=True)
    heading_font = load_font(26, bold=True)
    body_font = load_font(22)
    bullet_font = load_font(21)
    table_header_font = load_font(18, bold=True, mono=True)
    table_font = load_font(18, mono=True)
    small_font = load_font(18)

    fonts = {
        "title": title_font,
        "heading": heading_font,
        "body": body_font,
        "bullet": bullet_font,
        "table_header": table_header_font,
        "table_row": table_font,
        "blank": body_font,
    }

    blocks = _parse_report(report_text)
    pages = _paginate(blocks, fonts)

    generated_at = datetime.now().astimezone().strftime(
        "%d %b %Y, %I:%M %p %Z"
    )

    # Remove stale output pages only after parsing succeeds.
    for old_file in OUTPUT_DIR.glob("latest_report_page_*.png"):
        old_file.unlink(missing_ok=True)

    output_paths = []

    for page_number, page_blocks in enumerate(pages, start=1):
        body_height = sum(
            _line_height(block["kind"])
            for block in page_blocks
        )

        image_height = HEADER_HEIGHT + 35 + body_height + PADDING

        image = Image.new(
            "RGB",
            (IMAGE_WIDTH, image_height),
            "#F5F7FA",
        )

        draw = ImageDraw.Draw(image)

        draw.rectangle(
            (0, 0, IMAGE_WIDTH, HEADER_HEIGHT),
            fill="#132238",
        )

        draw.text(
            (PADDING, 28),
            "AUTONOMOUS FINANCIAL ANALYST",
            font=title_font,
            fill="#FFFFFF",
        )

        draw.text(
            (PADDING, 85),
            f"Market Sentiment Report | {generated_at}",
            font=small_font,
            fill="#D7E3F2",
        )

        draw.text(
            (IMAGE_WIDTH - 230, 120),
            f"Page {page_number}/{len(pages)}",
            font=small_font,
            fill="#D7E3F2",
        )

        y = HEADER_HEIGHT + 24

        for block in page_blocks:
            kind = block["kind"]
            text = block["text"]
            height = _line_height(kind)

            if kind == "blank":
                y += height
                continue

            if kind == "title":
                font = title_font
                fill = "#132238"

            elif kind == "heading":
                font = heading_font
                fill = "#1C477A"

            elif kind == "table_header":
                font = table_header_font
                fill = "#1C477A"

            elif kind == "table_row":
                font = table_font
                fill = "#17212F"

            elif kind == "bullet":
                font = bullet_font
                fill = "#17212F"

            else:
                font = body_font
                fill = "#17212F"

            if kind in {"table_header", "table_row"}:
                draw.rectangle(
                    (PADDING - 6, y - 2,
                     IMAGE_WIDTH - PADDING + 6, y + height - 2),
                    fill="#E7EDF5" if kind == "table_header" else "#F5F7FA",
                )

            draw.text(
                (PADDING, y),
                text,
                font=font,
                fill=fill,
            )

            y += height

        output_path = OUTPUT_DIR / (
            f"latest_report_page_{page_number:02d}.png"
        )

        image.save(output_path, format="PNG", optimize=True)
        output_paths.append(output_path)

    return output_paths