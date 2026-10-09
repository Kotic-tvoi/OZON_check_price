/**
 * Google Sheets -> Extensions -> Apps Script.
 * One-time: run setupConnection() as the owner and deploy as a web app.
 * Web app settings: Execute as "Me", access "Anyone".
 * Requests are authenticated with a long random shared secret.
 */

const COMPLETE_SHEET = 'Цены Ozon';
const INCOMPLETE_SHEET = 'Цены Ozon (неполные)';

function setupConnection() {
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  if (!spreadsheet) {
    throw new Error('Откройте Apps Script через Расширения -> Apps Script нужной таблицы');
  }
  const properties = PropertiesService.getScriptProperties();
  properties.setProperty('SPREADSHEET_ID', spreadsheet.getId());
  if (!properties.getProperty('UPLOAD_TOKEN')) {
    properties.setProperty(
      'UPLOAD_TOKEN',
      Utilities.getUuid().replace(/-/g, '') + Utilities.getUuid().replace(/-/g, '')
    );
  }
  Logger.log('Ссылка таблицы: ' + spreadsheet.getUrl());
  Logger.log('Ключ загрузки (храните в секрете): ' + properties.getProperty('UPLOAD_TOKEN'));
  Logger.log('Теперь опубликуйте: Развернуть -> Новое развертывание -> Веб-приложение.');
}

function jsonResponse(object) {
  return ContentService.createTextOutput(JSON.stringify(object))
    .setMimeType(ContentService.MimeType.JSON);
}

function doGet() {
  return jsonResponse({ok: false, error: 'Это адрес для POST-загрузки из локальной программы.'});
}

function validatePayload(data) {
  if (!data || typeof data !== 'object' || typeof data.complete !== 'boolean'
      || !Array.isArray(data.items) || data.items.length < 1 || data.items.length > 10000) {
    throw new Error('Некорректный каталог или нет товаров');
  }
  if (typeof data.store_url !== 'string' ||
      !/^https:\/\/www\.ozon\.ru\/seller\//.test(data.store_url)) {
    throw new Error('Некорректная ссылка магазина');
  }
  if (typeof data.pvz_url !== 'string' ||
      !/^https:\/\/www\.ozon\.ru\/geo\//.test(data.pvz_url)) {
    throw new Error('Некорректная ссылка ПВЗ');
  }
  const unique = new Map();
  for (const item of data.items) {
    if (!item || typeof item.article !== 'string' ||
        !/^\d{7,12}$/.test(item.article) ||
        !(item.price === null ||
          (typeof item.price === 'number' && Number.isSafeInteger(item.price) && item.price >= 0))) {
      throw new Error('Некорректный артикул или цена');
    }
    unique.set(item.article, [item.article, item.price === null ? 'Нет данных' : item.price]);
  }
  return Array.from(unique.values()).sort((a, b) => Number(a[0]) - Number(b[0]));
}

function doPost(e) {
  try {
    const properties = PropertiesService.getScriptProperties();
    const secret = properties.getProperty('UPLOAD_TOKEN');
    const spreadsheetId = properties.getProperty('SPREADSHEET_ID');
    if (!secret || !spreadsheetId) throw new Error('Сначала запустите setupConnection()');
    const data = JSON.parse((e && e.postData && e.postData.contents) || '{}');
    if (typeof data.token !== 'string' || data.token !== secret) {
      return jsonResponse({ok: false, error: 'Неверный ключ загрузки'});
    }
    const rows = validatePayload(data);
    const lock = LockService.getScriptLock();
    if (!lock.tryLock(25000)) {
      return jsonResponse({ok: false, error: 'Таблица занята другим обновлением'});
    }
    try {
      const spreadsheet = SpreadsheetApp.openById(spreadsheetId);
      const sheetName = data.complete ? COMPLETE_SHEET : INCOMPLETE_SHEET;
      const sheet = spreadsheet.getSheetByName(sheetName) || spreadsheet.insertSheet(sheetName);
      if (sheet.getMaxRows() < rows.length + 1) {
        sheet.insertRowsAfter(sheet.getMaxRows(), rows.length + 1 - sheet.getMaxRows());
      }
      const previousRows = Math.max(0, sheet.getLastRow() - 1);
      sheet.getRange(1, 1, 1, 2).setValues([['Артикул товара', 'Конечная цена']]);
      sheet.getRange(2, 1, rows.length, 1).setNumberFormat('@');
      sheet.getRange(2, 1, rows.length, 2).setValues(rows);
      if (previousRows > rows.length) {
        sheet.getRange(rows.length + 2, 1, previousRows - rows.length, 2).clearContent();
      }
      sheet.getRange('D1:E7').setValues([
        ['Статус', data.complete ? 'Полный каталог' : 'НЕПОЛНЫЙ КАТАЛОГ'],
        ['Время обновления', new Date()],
        ['Артикулов', rows.length],
        ['С ценой', rows.filter(r => typeof r[1] === 'number').length],
        ['ПВЗ', String(data.pvz_address || '').slice(0, 250)],
        ['Магазин', data.store_url],
        ['Примечание', data.complete ? 'Конец каталога подтверждён'
          : 'Отсутствующие артикулы нельзя считать снятыми с продажи']
      ]);
      sheet.getRange('E2').setNumberFormat('dd.mm.yyyy hh:mm:ss');
      sheet.getRange('A1:B1').setFontWeight('bold');
      sheet.getRange('D1:D7').setFontWeight('bold');
      sheet.setFrozenRows(1);
      sheet.setColumnWidth(1, 175);
      sheet.setColumnWidth(2, 155);
      sheet.setColumnWidth(4, 165);
      sheet.setColumnWidth(5, 420);
      SpreadsheetApp.flush();
      return jsonResponse({ok: true, sheet: sheetName, count: rows.length});
    } finally {
      lock.releaseLock();
    }
  } catch (error) {
    return jsonResponse({ok: false, error: String(error && error.message || error)});
  }
}
