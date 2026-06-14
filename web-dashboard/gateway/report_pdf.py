"""
Report PDF — unified PDF conversion utilities (single copy in codebase).

Provides _try_convert_pdf() — tries WeasyPrint → pdfkit → xhtml2pdf.
Also provides the Markdown→HTML converter extracted from work_order_report_generator.py.
"""

import io


def try_convert_pdf(html: str) -> bytes | None:
    """Convert HTML to PDF bytes. Returns None if all 3 backends fail.

    Backends tried in order:
    1. WeasyPrint (best quality, needs GTK3 on Windows)
    2. pdfkit / wkhtmltopdf
    3. xhtml2pdf (limited CSS support, last resort)
    """
    # Backend 1: WeasyPrint
    try:
        from weasyprint import HTML as WHTML
        return WHTML(string=html).write_pdf()
    except Exception:
        pass

    # Backend 2: wkhtmltopdf via pdfkit
    try:
        import pdfkit
        return pdfkit.from_string(html, False)
    except Exception:
        pass

    # Backend 3: xhtml2pdf
    try:
        from xhtml2pdf import pisa
        buf = io.BytesIO()
        pisa.CreatePDF(html, dest=buf)
        buf.seek(0)
        return buf.read()
    except Exception:
        pass

    return None


# ══════════════════════════════════════════════════════════════════════════
# Simple Markdown → HTML converter (extracted from work_order_report_generator)
# ══════════════════════════════════════════════════════════════════════════

def simple_markdown_to_html(md: str) -> str:
    """Convert basic Markdown to HTML. Handles h2/h3, bold, inline code, lists, tables, blockquotes."""
    lines = md.split("\n")
    out = []
    in_list = False
    list_type = None
    in_table = False
    in_blockquote = False

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Blockquote
        if stripped.startswith("> "):
            if not in_blockquote:
                out.append("<blockquote>")
                in_blockquote = True
            out.append(stripped[2:] + "<br>")
            i += 1
            continue
        elif in_blockquote and not stripped.startswith("> "):
            out.append("</blockquote>")
            in_blockquote = False

        # Code blocks
        if stripped.startswith("```"):
            i += 1
            code_lines = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1
            out.append(f"<pre><code>{_escape_html('\n'.join(code_lines))}</code></pre>")
            continue

        # Tables
        if stripped.startswith("|") and stripped.endswith("|"):
            if not in_table:
                out.append('<table>')
                in_table = True
            is_header = (i + 1 < len(lines) and
                         lines[i + 1].strip().startswith("|") and
                         "---" in lines[i + 1])
            tag = "th" if is_header else "td"
            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            out.append("<tr>" + "".join(f"<{tag}>{_escape_html(c)}</{tag}>" for c in cells) + "</tr>")
            if is_header:
                i += 2
                continue
            i += 1
            continue
        elif in_table:
            out.append("</table>")
            in_table = False

        # Headers
        if stripped.startswith("### "):
            out.append(f"<h3>{_inline_format(stripped[4:])}</h3>")
            i += 1; continue
        if stripped.startswith("## "):
            out.append(f"<h2><span class=\"sec-num\">§</span>{_inline_format(stripped[3:])}</h2>")
            i += 1; continue

        # Lists
        is_ul = stripped.startswith("- ") or stripped.startswith("* ")
        is_ol = len(stripped) > 2 and stripped[0].isdigit() and stripped[1:3] == ". "
        if is_ul or is_ol:
            if not in_list:
                list_type = "ul" if is_ul else "ol"
                out.append(f"<{list_type}>")
                in_list = True
            elif (is_ul and list_type == "ol") or (is_ol and list_type == "ul"):
                out.append(f"</{list_type}><{('ul' if is_ul else 'ol')}>")
                list_type = "ul" if is_ul else "ol"
            content = stripped[2:] if is_ul else stripped[stripped.index(". ") + 2:]
            out.append(f"<li>{_inline_format(content)}</li>")
            i += 1; continue
        elif in_list:
            out.append(f"</{list_type}>")
            in_list = False
            list_type = None

        # Empty lines
        if not stripped:
            i += 1; continue

        # Paragraphs
        out.append(f"<p>{_inline_format(stripped)}</p>")
        i += 1

    # Close open blocks
    if in_list:
        out.append(f"</{list_type}>")
    if in_table:
        out.append("</table>")
    if in_blockquote:
        out.append("</blockquote>")

    return "\n".join(out)


def _inline_format(text: str) -> str:
    """Handle inline Markdown: bold (**), code (`), italic (*)."""
    import re
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)
    return text


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
