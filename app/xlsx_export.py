"""Optional Excel response generated in RAM using only the Python standard library."""
from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED

from core import PriceResult


def _cell(ref: str, value) -> str:
    if value is None:
        return ""
    if isinstance(value, int):
        return f'<c r="{ref}"><v>{value}</v></c>'
    return f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'


def to_xlsx(results: list[PriceResult]) -> bytes:
    """Legacy 2 columns, no file saved on server."""
    rows = [["Артикул товара", "Конечная цена"]]
    rows.extend([[row.article,
                  row.price if row.price is not None else
                  'Нет данных' if row.status in ('unavailable', 'no_price') else None]
                 for row in results])
    body = []
    for index, values in enumerate(rows, 1):
        # SKU is stored as text to preserve its exact digits.
        body.append(f'<row r="{index}">{_cell(f"A{index}", values[0])}{_cell(f"B{index}", values[1])}</row>')
    sheet = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
             '<cols><col min="1" max="1" width="22" customWidth="1"/>'
             '<col min="2" max="2" width="20" customWidth="1"/></cols>'
             '<sheetData>' + ''.join(body) + '</sheetData></worksheet>')
    files = {
        '[Content_Types].xml': ('<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '</Types>'),
        '_rels/.rels': ('<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>'),
        'xl/workbook.xml': ('<?xml version="1.0" encoding="UTF-8"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="OZON Prices" sheetId="1" r:id="rId1"/></sheets></workbook>'),
        'xl/_rels/workbook.xml.rels': ('<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet1.xml"/></Relationships>'),
        'xl/worksheets/sheet1.xml': sheet,
    }
    stream = BytesIO()
    with ZipFile(stream, 'w', ZIP_DEFLATED) as workbook:
        for name, content in files.items():
            workbook.writestr(name, content)
    return stream.getvalue()