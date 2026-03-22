"""Export services (CSV + PDF)."""

import io
import csv
import html
import logging
from datetime import date

logger = logging.getLogger(__name__)

_DASH = '\u2014'


def generate_csv(records: list) -> str:
    """Generate CSV string from attendance records."""
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        'Student ID', 'Name', 'Department', 'Date',
        'Time In', 'Time Out', 'Status', 'Confidence', 'Method', 'Liveness Score'
    ])

    for r in records:
        writer.writerow([
            r.get('sid', ''),
            r.get('name', ''),
            r.get('department', ''),
            r.get('date', ''),
            r.get('time_in', ''),
            r.get('time_out', ''),
            r.get('status', ''),
            r.get('confidence', ''),
            r.get('method', ''),
            r.get('liveness_score', ''),
        ])

    return output.getvalue()


def generate_pdf(records: list, summary: dict, title: str = 'Attendance Report') -> bytes:
    """Generate PDF report using WeasyPrint."""
    try:
        from weasyprint import HTML
    except ImportError:
        logger.warning('WeasyPrint not installed, returning empty PDF')
        return b''

    today = date.today().isoformat()

    rows_html = ''
    for r in records:
        sid = html.escape(str(r.get('sid', '')))
        name = html.escape(str(r.get('name', '')))
        dept = html.escape(str(r.get('department', _DASH)))
        rec_date = html.escape(str(r.get('date', '')))
        time_in = html.escape(str(r.get('time_in', '')))
        status = html.escape(str(r.get('status', '')))
        conf = html.escape(str(r.get('confidence', _DASH)))
        method = html.escape(str(r.get('method', '')))
        rows_html += f"""
        <tr>
            <td>{sid}</td>
            <td>{name}</td>
            <td>{dept}</td>
            <td>{rec_date}</td>
            <td>{time_in}</td>
            <td>{status}</td>
            <td>{conf}</td>
            <td>{method}</td>
        </tr>"""

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: sans-serif; margin: 20px; }}
            h1 {{ color: #00d2ff; }}
            .summary {{ display: flex; gap: 20px; margin: 20px 0; }}
            .stat {{ background: #f5f5f5; padding: 12px 20px; border-radius: 8px; }}
            .stat .value {{ font-size: 1.5rem; font-weight: bold; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; font-size: 0.85rem; }}
            th {{ background: #1a1a2e; color: white; }}
            tr:nth-child(even) {{ background: #f9f9f9; }}
            .footer {{ margin-top: 30px; font-size: 0.75rem; color: #888; }}
        </style>
    </head>
    <body>
        <h1>\U0001f393 {html.escape(title)}</h1>
        <p>Generated: {today}</p>

        <div class="summary">
            <div class="stat"><div class="value">{summary.get('total', 0)}</div>Total Records</div>
            <div class="stat"><div class="value">{summary.get('present', 0)}</div>Present</div>
            <div class="stat"><div class="value">{summary.get('late', 0)}</div>Late</div>
            <div class="stat"><div class="value">{summary.get('rate', '0')}%</div>Attendance Rate</div>
        </div>

        <table>
            <thead>
                <tr><th>Student ID</th><th>Name</th><th>Dept</th><th>Date</th><th>Time In</th><th>Status</th><th>Confidence</th><th>Method</th></tr>
            </thead>
            <tbody>{rows_html}</tbody>
        </table>

        <div class="footer">
            <p>Face Recognition Attendance System — Powered by AI</p>
        </div>
    </body>
    </html>
    """

    try:
        pdf = HTML(string=html_content).write_pdf()
        return pdf
    except Exception as e:
        logger.error(f'PDF generation failed: {e}')
        return b''
