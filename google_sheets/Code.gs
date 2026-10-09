/** Read-only Ozon seller catalog prices. A = SKU, B = price, H2 = PVZ, H4 = seller URL. */
const SHEET_NAME = 'Цены Ozon';
const DEFAULT_PVZ = 'https://www.ozon.ru/geo/moskva/442329/';
const DEFAULT_STORE = 'https://www.ozon.ru/seller/jkeratin/';

function onOpen() {
  SpreadsheetApp.getUi().createMenu('Ozon — цены')
    .addItem('Настроить API', 'ozonConfigure')
    .addItem('Обновить цены', 'ozonUpdate')
    .addToUi();
}

function ozonConfigure() {
  const ui = SpreadsheetApp.getUi();
  const url = ui.prompt('HTTPS-адрес сервиса', 'https://prices.example.ru', ui.ButtonSet.OK_CANCEL);
  if (url.getSelectedButton() !== ui.Button.OK) return;
  const server = url.getResponseText().trim().replace(/\/+$/, '');
  if (!/^https:\/\/[^\s/]+$/.test(server)) throw new Error('Нужен HTTPS-адрес без пути');
  const response = ui.prompt('API токен', 'Тот же токен, что OZON_API_TOKEN', ui.ButtonSet.OK_CANCEL);
  if (response.getSelectedButton() !== ui.Button.OK) return;
  if (!response.getResponseText().trim()) throw new Error('Токен пустой');
  PropertiesService.getScriptProperties().setProperties({
    OZON_SERVER_URL: server, OZON_API_TOKEN: response.getResponseText().trim()
  });
  ui.alert('Подключение сохранено');
}

function ozonUpdate() {
  const lock = LockService.getDocumentLock();
  if (!lock.tryLock(1000)) throw new Error('Обновление уже выполняется');
  try {
    const spreadsheet = SpreadsheetApp.getActive();
    const sheet = spreadsheet.getSheetByName(SHEET_NAME) || spreadsheet.insertSheet(SHEET_NAME);
    sheet.getRange('A1:B1').setValues([['Артикул товара', 'Конечная цена']]);
    sheet.getRange('H1').setValue('Ссылка на ПВЗ');
    sheet.getRange('H3').setValue('Ссылка на магазин');
    if (!sheet.getRange('H2').getDisplayValue()) sheet.getRange('H2').setValue(DEFAULT_PVZ);
    if (!sheet.getRange('H4').getDisplayValue()) sheet.getRange('H4').setValue(DEFAULT_STORE);
    const pvz = sheet.getRange('H2').getDisplayValue().trim();
    const store = sheet.getRange('H4').getDisplayValue().trim();
    const lastRow = sheet.getLastRow();
    if (lastRow < 2) throw new Error('Добавьте артикулы в колонку A');
    const values = sheet.getRange(2, 1, lastRow - 1, 1).getDisplayValues();
    const articles = [], positions = [];
    values.forEach((row, idx) => {
      const sku = row[0].trim();
      if (sku) { articles.push(sku); positions.push(idx); }
    });
    if (!articles.length || articles.length > 100) throw new Error('Укажите от 1 до 100 SKU');
    const props = PropertiesService.getScriptProperties();
    const base = props.getProperty('OZON_SERVER_URL');
    const token = props.getProperty('OZON_API_TOKEN');
    if (!base || !token) throw new Error('Сначала выберите «Настроить API»');
    const response = UrlFetchApp.fetch(base + '/v1/prices', {
      method: 'post', contentType: 'application/json',
      headers: {'Authorization': 'Bearer ' + token},
      payload: JSON.stringify({articles, pvz_url: pvz, store_url: store}),
      muteHttpExceptions: true
    });
    const result = JSON.parse(response.getContentText());
    if (response.getResponseCode() !== 200) {
      throw new Error(result.message || result.error || 'Ошибка сервера');
    }
    if (result.pvz_url !== pvz || result.store_url !== store ||
        !Array.isArray(result.results) || result.results.length !== articles.length) {
      throw new Error('Получен неожиданный ответ сервера');
    }
    const output = values.map(() => ['']);
    for (let i = 0; i < articles.length; i++) {
      const r = result.results[i];
      if (String(r.article) !== articles[i] || !['ok','no_price','not_in_catalog'].includes(r.status))
        throw new Error('Ошибка сопоставления или неполные данные');
      output[positions[i]] = [r.status === 'ok' ? r.price : 'Нет данных'];
    }
    sheet.getRange(2, 2, output.length, 1).setValues(output);
    spreadsheet.toast('Проверено SKU: ' + articles.length + '. Цен: ' + result.summary.found);
  } finally {
    lock.releaseLock();
  }
}