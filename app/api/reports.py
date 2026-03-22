"""Reports API routes."""

import io
from datetime import date

from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required
from app.auth.decorators import role_required
from app.services import attendance as svc
from app.services import export as export_svc

reports_bp = Blueprint('reports_api', __name__)


@reports_bp.route('/export/csv', methods=['GET'])
@jwt_required()
@role_required('admin', 'teacher')
def export_csv():
    """Export attendance data as CSV."""
    start = request.args.get('start', date.today().isoformat())
    end = request.args.get('end', date.today().isoformat())
    student_id = request.args.get('student_id', type=int)

    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
    except ValueError:
        return jsonify(error='Invalid date format. Use YYYY-MM-DD.'), 400

    records = svc.get_attendance_range(
        start_date, end_date, student_id
    )

    csv_data = export_svc.generate_csv(records)
    return send_file(
        io.BytesIO(csv_data.encode()),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'attendance_{start}_to_{end}.csv',
    )


@reports_bp.route('/export/pdf', methods=['GET'])
@jwt_required()
@role_required('admin', 'teacher')
def export_pdf():
    """Export attendance data as PDF."""
    start = request.args.get('start', date.today().isoformat())
    end = request.args.get('end', date.today().isoformat())
    student_id = request.args.get('student_id', type=int)

    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
    except ValueError:
        return jsonify(error='Invalid date format. Use YYYY-MM-DD.'), 400

    records = svc.get_attendance_range(
        start_date, end_date, student_id
    )

    # Compute summary
    present = sum(1 for r in records if r.get('status') == 'present')
    late = sum(1 for r in records if r.get('status') == 'late')
    rate = round((present + late) / len(records) * 100, 1) if records else 0

    summary = {'total': len(records), 'present': present, 'late': late, 'rate': rate}

    pdf_bytes = export_svc.generate_pdf(records, summary, title=f'Attendance Report ({start} to {end})')

    if not pdf_bytes:
        return jsonify(error='PDF generation failed'), 500

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'attendance_{start}_to_{end}.pdf',
    )
