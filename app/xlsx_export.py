"""Optional two-column Excel response created in memory (stdlib only)."""
from io import BytesIO
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED


def to_xlsx(rows: list[dict]) -> bytes:
    def cell(ref, value):
        if value is None:
            return ''
        if isinstance(value, int):
            return f'<c r="{ref}"><v>{value}</v></c>'
        return f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'

    table = [('Артикул товара', 'Конечная цена')]
    table.extend((r['article'], r['price'] if r['price'] is not None else 'Нет данных') for r in rows)
    body = ''.join(f'<row r="{i}">{cell(f"A{i}",a)}{cell(f"B{i}",b)}</row>'
                   for i,(a,b) in enumerate(table,1))
    sheet = ('<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData>' + body + '</sheetData></worksheet>')
    files = {
        '[Content_Types].xml': ('<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '</Types>'),
        '_rels/.rels': ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>'),
        'xl/workbook.xml': ('<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="OZON Prices" sheetId="1" r:id="rId1"/></sheets></workbook>'),
        'xl/_rels/workbook.xml.rels': ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet1.xml"/></Relationships>'),
        'xl/worksheets/sheet1.xml': sheet,
    }
    stream = BytesIO()
    with ZipFile(stream,'w',ZIP_DEFLATED) as archive:
        for name, content in files.items():
            # Include XML declarations for strict Excel/OpenXML readers.
            if not content.startswith('<?xml'):
                content = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' + content
            archive.writestr(name, content)
    return stream.getvalue()