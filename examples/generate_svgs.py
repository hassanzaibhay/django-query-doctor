#!/usr/bin/env python
"""
Generate SVG terminal renders for README and documentation.
These look like real terminal screenshots but are crisp SVG.
"""
import os
import html

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "screenshots")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def create_terminal_svg(
    title: str,
    lines: list[dict],
    filename: str,
    width: int = 820,
    prompt: str | None = None,
):
    """
    Generate an SVG that looks like a terminal window.

    lines: list of dicts with keys:
        - text: the text content
        - color: hex color (default #D4D4D4)
        - bold: bool (default False)
        - indent: int spaces (default 0)
    """
    line_height = 20
    padding_top = 50  # Space for title bar
    padding_bottom = 20
    padding_left = 16
    font_size = 13

    # Calculate height
    total_lines = len(lines) + (1 if prompt else 0)
    height = padding_top + (total_lines * line_height) + padding_bottom

    svg_lines = []
    svg_lines.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">')
    svg_lines.append('<defs><style>')
    svg_lines.append('  .terminal-text { font-family: "JetBrains Mono", "Cascadia Code", "Fira Code", Consolas, monospace; }')
    svg_lines.append('</style></defs>')

    # Background
    svg_lines.append(f'<rect width="{width}" height="{height}" rx="8" fill="#1E1E1E"/>')

    # Title bar
    svg_lines.append('<rect width="' + str(width) + '" height="36" rx="8" fill="#2D2D2D"/>')
    svg_lines.append('<rect x="0" y="8" width="' + str(width) + '" height="28" fill="#2D2D2D"/>')

    # Traffic lights
    svg_lines.append('<circle cx="20" cy="18" r="6" fill="#FF5F57"/>')
    svg_lines.append('<circle cx="40" cy="18" r="6" fill="#FFBD2E"/>')
    svg_lines.append('<circle cx="60" cy="18" r="6" fill="#28CA41"/>')

    # Title
    escaped_title = html.escape(title)
    svg_lines.append(f'<text x="{width // 2}" y="22" text-anchor="middle" class="terminal-text" fill="#8C8C8C" font-size="12">{escaped_title}</text>')

    # Prompt line
    y_offset = padding_top
    if prompt:
        escaped_prompt = html.escape(prompt)
        svg_lines.append(f'<text x="{padding_left}" y="{y_offset}" class="terminal-text" font-size="{font_size}">')
        svg_lines.append(f'  <tspan fill="#6A9955">$</tspan><tspan fill="#D4D4D4"> {escaped_prompt}</tspan>')
        svg_lines.append('</text>')
        y_offset += line_height

    # Content lines
    for line_data in lines:
        text = line_data.get("text", "")
        color = line_data.get("color", "#D4D4D4")
        bold = line_data.get("bold", False)
        indent = line_data.get("indent", 0)

        if not text:
            y_offset += line_height
            continue

        escaped_text = html.escape(text)
        weight = 'font-weight="700"' if bold else ''
        x = padding_left + (indent * 8)
        svg_lines.append(f'<text x="{x}" y="{y_offset}" class="terminal-text" font-size="{font_size}" fill="{color}" {weight}>{escaped_text}</text>')
        y_offset += line_height

    svg_lines.append('</svg>')

    svg_content = "\n".join(svg_lines)
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(svg_content)
    print(f"Generated: {filepath}")
    return filepath


# ── SVG 1: Console Output ──────────────────────────────────
create_terminal_svg(
    title="query-doctor — Console Output",
    prompt="python manage.py runserver",
    filename="console_output.svg",
    lines=[
        {"text": ""},
        {"text": "════════════════════════════════════════════════════════════", "color": "#569CD6"},
        {"text": "  Query Doctor Report", "color": "#569CD6", "bold": True},
        {"text": "  Total queries: 53 | Time: 127.3ms | Issues: 3", "color": "#569CD6"},
        {"text": "════════════════════════════════════════════════════════════", "color": "#569CD6"},
        {"text": ""},
        {"text": "CRITICAL  N+1 detected: 47 queries for table \"myapp_author\"", "color": "#F44747", "bold": True},
        {"text": "Location: myapp/views.py:83 in get_queryset", "color": "#808080", "indent": 3},
        {"text": "Code: books = Book.objects.all()", "color": "#808080", "indent": 3},
        {"text": "Fix: Add .select_related('author') to your queryset", "color": "#4EC9B0", "indent": 3},
        {"text": "Queries: 47 | Est. savings: ~89.0ms", "color": "#808080", "indent": 3},
        {"text": ""},
        {"text": "WARNING   Duplicate query: 6 identical queries", "color": "#CE9178", "bold": True},
        {"text": "Location: myapp/views.py:91 in get_context_data", "color": "#808080", "indent": 3},
        {"text": "Fix: Assign the queryset result to a variable and reuse it", "color": "#4EC9B0", "indent": 3},
        {"text": "Queries: 6 | Est. savings: ~4.2ms", "color": "#808080", "indent": 3},
        {"text": ""},
        {"text": "INFO      Column \"published_date\" has no index on \"myapp_book\"", "color": "#569CD6", "bold": True},
        {"text": "Fix: Add db_index=True to the published_date field", "color": "#4EC9B0", "indent": 3},
    ],
)


# ── SVG 2: Context Manager / Test Usage ────────────────────
create_terminal_svg(
    title="query-doctor — Test Usage",
    prompt="pytest tests/test_queries.py -v",
    filename="test_usage.svg",
    lines=[
        {"text": ""},
        {"text": "tests/test_queries.py::test_book_list_no_nplusone PASSED", "color": "#28CA41"},
        {"text": "tests/test_queries.py::test_book_list_query_count PASSED", "color": "#28CA41"},
        {"text": "tests/test_queries.py::test_no_duplicate_queries PASSED", "color": "#28CA41"},
        {"text": "tests/test_queries.py::test_api_under_budget FAILED", "color": "#F44747"},
        {"text": ""},
        {"text": "FAILED tests/test_queries.py::test_api_under_budget", "color": "#F44747", "bold": True},
        {"text": "AssertionError: Too many queries: 47.", "color": "#F44747", "indent": 2},
        {"text": "Issues: ['N+1 detected: 47 queries for table author']", "color": "#F44747", "indent": 2},
        {"text": ""},
        {"text": "3 passed, 1 failed in 0.42s", "color": "#CE9178", "bold": True},
    ],
)


# ── SVG 3: Auto-Fix Dry Run ───────────────────────────────
create_terminal_svg(
    title="query-doctor — Auto-Fix Preview",
    prompt="python manage.py fix_queries --url /api/books/",
    filename="auto_fix.svg",
    lines=[
        {"text": ""},
        {"text": "Analyzing /api/books/ ...", "color": "#808080"},
        {"text": "Found 3 fixable issues", "color": "#D4D4D4"},
        {"text": ""},
        {"text": "--- myapp/views.py", "color": "#F44747"},
        {"text": "+++ myapp/views.py (fixed)", "color": "#28CA41"},
        {"text": "@@ Line 15: N+1 on author @@", "color": "#569CD6"},
        {"text": "-    books = Book.objects.all()", "color": "#F44747", "indent": 1},
        {"text": "+    books = Book.objects.select_related('author').all()", "color": "#28CA41", "indent": 1},
        {"text": ""},
        {"text": "@@ Line 28: len() instead of count() @@", "color": "#569CD6"},
        {"text": "-    total = len(Book.objects.filter(active=True))", "color": "#F44747", "indent": 1},
        {"text": "+    total = Book.objects.filter(active=True).count()", "color": "#28CA41", "indent": 1},
        {"text": ""},
        {"text": "@@ Line 42: Fat SELECT @@", "color": "#569CD6"},
        {"text": "-    books = Book.objects.filter(category=cat)", "color": "#F44747", "indent": 1},
        {"text": "+    books = Book.objects.filter(category=cat).only('title', 'price', 'slug')", "color": "#28CA41", "indent": 1},
        {"text": ""},
        {"text": "3 fixes available. Run with --apply to apply them.", "color": "#DCDCAA", "bold": True},
    ],
)


# ── SVG 4: Project-Wide Diagnosis ──────────────────────────
create_terminal_svg(
    title="query-doctor — Project Health Scan",
    prompt="python manage.py diagnose_project",
    filename="project_diagnosis.svg",
    lines=[
        {"text": ""},
        {"text": "Discovering URLs... found 47 endpoints", "color": "#808080"},
        {"text": "Running diagnosis...", "color": "#808080"},
        {"text": "  Analyzing /api/books/        [1/47]", "color": "#808080"},
        {"text": "  Analyzing /api/orders/       [2/47]", "color": "#808080"},
        {"text": "  Analyzing /blog/             [3/47]", "color": "#808080"},
        {"text": "  ...", "color": "#808080"},
        {"text": ""},
        {"text": "═══════════════════════════════════════════════════", "color": "#569CD6"},
        {"text": "  Project Health Report", "color": "#569CD6", "bold": True},
        {"text": "  Overall Score: 73/100", "color": "#CE9178", "bold": True},
        {"text": "═══════════════════════════════════════════════════", "color": "#569CD6"},
        {"text": ""},
        {"text": "  App              Health   Queries   Issues", "color": "#808080"},
        {"text": "  ─────────────────────────────────────────────", "color": "#808080"},
        {"text": "  accounts          95/100      12        1", "color": "#28CA41"},
        {"text": "  billing           88/100      45        2", "color": "#28CA41"},
        {"text": "  api               71/100     389        8", "color": "#CE9178"},
        {"text": "  shop              42/100     623       12", "color": "#F44747"},
        {"text": ""},
        {"text": "Report saved to query_doctor_report.html", "color": "#28CA41", "bold": True},
        {"text": "(47 URLs, 23 issues, health: 73/100)", "color": "#808080"},
    ],
)


# ── SVG 5: Query Budget Decorator ─────────────────────────
create_terminal_svg(
    title="query-doctor — Query Budget",
    prompt="python -c 'from myapp.views import my_view; my_view()'",
    filename="query_budget.svg",
    lines=[
        {"text": ""},
        {"text": "Traceback (most recent call last):", "color": "#D4D4D4"},
        {"text": '  File "myapp/views.py", line 15, in my_view', "color": "#D4D4D4"},
        {"text": "    return render(request, 'books.html', ctx)", "color": "#D4D4D4"},
        {"text": "query_doctor.exceptions.QueryBudgetError:", "color": "#F44747", "bold": True},
        {"text": "  Query budget exceeded: 47 queries (max: 10)", "color": "#F44747"},
        {"text": ""},
        {"text": "  Top issues:", "color": "#CE9178"},
        {"text": "    CRITICAL: N+1 on author (47 queries)", "color": "#F44747", "indent": 2},
        {"text": "    Fix: .select_related('author')", "color": "#4EC9B0", "indent": 2},
    ],
)


# ── SVG 6: Quick Start (3 steps) ──────────────────────────
create_terminal_svg(
    title="query-doctor — Quick Start",
    prompt=None,
    filename="quick_start.svg",
    width=720,
    lines=[
        {"text": "# Step 1: Install", "color": "#6A9955"},
        {"text": "$ pip install django-query-doctor", "color": "#D4D4D4"},
        {"text": ""},
        {"text": "# Step 2: Add one line to settings.py", "color": "#6A9955"},
        {"text": 'MIDDLEWARE = [', "color": "#CE9178"},
        {"text": '    ...', "color": "#808080"},
        {"text": '    "query_doctor.QueryDoctorMiddleware",', "color": "#4EC9B0"},
        {"text": ']', "color": "#CE9178"},
        {"text": ""},
        {"text": "# Step 3: Run your app", "color": "#6A9955"},
        {"text": "$ python manage.py runserver", "color": "#D4D4D4"},
        {"text": "# That's it! Check your terminal for prescriptions.", "color": "#6A9955"},
    ],
)

print(f"\nAll SVGs generated in {OUTPUT_DIR}/")
