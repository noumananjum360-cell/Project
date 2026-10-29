"""Receipt / invoice as HTML (printed or saved to PDF through Qt)."""
from __future__ import annotations

import datetime as dt
from html import escape

from app.money import fmt, fmt_rate


def receipt_html(sale: dict, settings, width_mm: int = 80) -> str:
    s = settings
    rows = "".join(
        f"<tr><td>{escape(i['name'])}<br><span class='m'>{i['qty']} x {fmt(i['unit_price'])}"
        + (f" - disc {fmt(i['line_discount'])}" if i["line_discount"] else "")
        + (f" · tax {fmt_rate(i['tax_rate_bp'])}" if i["tax_rate_bp"] else "")
        + (f" · refunded {i['refunded_qty']}" if i.get("refunded_qty") else "")
        + f"</span></td><td class='r'>{fmt(i['line_total'])}</td></tr>" for i in sale["items"])
    refunds = "".join(f"<tr><td>Refund {escape(r['refund_no'])}</td><td class='r'>-{fmt(r['amount'])}</td></tr>"
                      for r in sale.get("refunds", []))
    status = "" if sale["status"] == "completed" else f"<p class='st'>{sale['status'].replace('_', ' ').upper()}</p>"
    cust = (f"<p>Customer: {escape(sale['customer'] or '')} ({escape(sale['loyalty_id'] or '')})</p>"
            if sale.get("customer") else "")
    demo = "<p class='st'>DEMO RECORD - NOT A REAL SALE</p>" if sale.get("is_demo") else ""
    when = dt.datetime.fromtimestamp(sale["sold_at"]).strftime("%d %b %Y %H:%M")
    return f"""<html><head><style>
      body {{ font-family: 'Segoe UI', Arial; font-size: 9pt; color: #111; }}
      h2 {{ margin: 0; font-size: 12pt; }} .m {{ color: #555; font-size: 8pt; }}
      table {{ width: 100%; border-collapse: collapse; }} td {{ padding: 3px 0; vertical-align: top; }}
      .r {{ text-align: right; white-space: nowrap; }} .t td {{ border-top: 1px solid #999; }}
      .st {{ font-weight: bold; color: #B00020; }} .c {{ text-align: center; }}
    </style></head><body>
      <div class='c'><h2>{escape(s.get('store_name') or '')}</h2>
      <div class='m'>{escape(s.get('store_address') or '')}<br>{escape(s.get('store_phone') or '')}</div></div>
      <p>Receipt <b>{escape(sale['receipt_no'])}</b><br>{when} · Cashier: {escape(sale.get('cashier') or '-')}</p>
      {cust}{status}{demo}
      <table width="100%" cellspacing="0">{rows}
        <tr class='t'><td>Subtotal</td><td class='r'>{fmt(sale['subtotal'])}</td></tr>
        <tr><td>Discounts</td><td class='r'>-{fmt(sale['discount_total'])}</td></tr>
        <tr><td>{escape(s.get('tax_label') or 'Tax')}</td><td class='r'>{fmt(sale['tax_total'])}</td></tr>
        <tr class='t'><td><b>TOTAL</b></td><td class='r'><b>{fmt(sale['total'])}</b></td></tr>
        <tr><td>Paid by</td><td class='r'>{escape(sale['payment_method'])}</td></tr>{refunds}
      </table>
      <p class='c m'>{escape(s.get('receipt_footer') or '')}</p>
    </body></html>"""
