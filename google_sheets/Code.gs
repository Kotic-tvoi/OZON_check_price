/**
 * Google Sheets -> Ozon read-only price reader.
 * A: article; B: final price; H2: one PVZ link for the entire request.
 * One HTTP request for up to 100 articles; no per-16-SKU packages or cursor.
 * No prices are stored by the Python service.
 */
const OZ_SHEET_NAME = 'Цены Ozon';
const OZ_MAX_ARTICLES = 100;
const OZ_PVZ_CELL = 'H2';
const OZ_DEFAULT_PVZ = 'https://www.ozon.ru/geo/moskva/442329/';

function onOpen() {
  SpreadsheetApp.getUi().createMenu('Ozon — цены')
    .addItem('Настроить подключение', 'ozonConfigure')
    .addItem('Обновить все цены', 'ozonStart')
    .addItem('Проверить ПВЗ', 'ozonCheckPvz')
    .addToUi();
}

function ozonConfigure() {
  const ui = SpreadsheetApp.getUi();
  const address = ui.prompt('Адрес Python-сервиса',
    'HTTPS-адрес, например https://prices.example.ru', ui.ButtonSet.OK_CANCEL);
  if (address.getSelectedButton() !== ui.Button.OK) return;
  const url = address.getResponseText().trim().replace(/\/+$/, '');
  if (!/^https:\/\/[^\s/]+$/.test(url)) {
    ui.alert('Укажите HTTPS-адрес сервера без пути'); return;
  }
  const tokenPrompt = ui.prompt('Секретный API-токен',
    'Токен должен совпадать с OZON_API_TOKEN на сервере.', ui.ButtonSet.OK_CANCEL);
  if (tokenPrompt.getSelectedButton() !== ui.Button.OK) return;
  const token = tokenPrompt.getResponseText().trim();
  if (!token) { ui.alert('Токен не может быть пустым'); return; }
  PropertiesService.getScriptProperties().setProperties({OZON_SERVER_URL: url, OZON_API_TOKEN: token});
  ui.alert('Подключение сохранено. Редакторы Apps Script имеют доступ к настройкам.');
}

function ozonSheet_() {
  const ss = SpreadsheetApp.getActive();
  let sheet = ss.getSheetByName(OZ_SHEET_NAME);
  if (!sheet) sheet = ss.insertSheet(OZ_SHEET_NAME);
  if (sheet.getRange('B1').getDisplayValue() === 'Ссылка на ПВЗ Ozon') {
    throw new Error('В старой таблице ПВЗ хранится построчно. Перенесите артикулы в A и освободите B для цен. ПВЗ — в H2.');
  }
  sheet.getRange(1, 1, 1, 2).setValues([['Артикул товара', 'Конечная цена']]);
  sheet.getRange('H1').setValue('Ссылка на ПВЗ Ozon');
  if (!sheet.getRange(OZ_PVZ_CELL).getDisplayValue().trim())
    sheet.getRange(OZ_PVZ_CELL).setValue(OZ_DEFAULT_PVZ);
  sheet.getRange('A:A').setNumberFormat('@');
  sheet.getRange('H:H').setNumberFormat('@');
  sheet.setFrozenRows(1);
  return sheet;
}

function ozonPvzUrl_(sheet) {
  const url = sheet.getRange(OZ_PVZ_CELL).getDisplayValue().trim();
  const match = /^https:\/\/(?:www\.)?ozon\.ru\/geo\/([a-z0-9-]+)\/(\d+)\/?$/i.exec(url);
  if (!match) throw new Error('Укажите ссылку на ПВЗ Ozon в H2');
  return 'https://www.ozon.ru/geo/' + match[1].toLowerCase() + '/' + match[2] + '/';
}

function ozonFetch_(path, payload) {
  const props = PropertiesService.getScriptProperties();
  const base = props.getProperty('OZON_SERVER_URL');
  const token = props.getProperty('OZON_API_TOKEN');
  if (!base || !token) throw new Error('Выберите: Ozon — цены → Настроить подключение');
  const response = UrlFetchApp.fetch(base + path, {
    method: 'post',
    contentType: 'application/json',
    headers: {'Authorization': 'Bearer ' + token},
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });
  const content = response.getContentText();
  let data;
  try { data = JSON.parse(content); }
  catch (_) { throw new Error('Некорректный ответ сервера (HTTP ' + response.getResponseCode() + ')'); }
  if (response.getResponseCode() !== 200)
    throw new Error('Ошибка API ' + response.getResponseCode() + ': ' +
      (data.message || data.error || content.slice(0, 150)));
  return data;
}

function ozonStart() {
  const lock = LockService.getDocumentLock();
  if (!lock.tryLock(1000)) throw new Error('Обновление уже запущено');
  try {
    const sheet = ozonSheet_();
    const url = ozonPvzUrl_(sheet);
    const lastRow = sheet.getLastRow();
    if (lastRow < 2) throw new Error('Добавьте артикулы в колонку A');
    const input = sheet.getRange(2, 1, lastRow - 1, 1).getDisplayValues();
    const articles = [];
    const positions = [];
    input.forEach((row, i) => {
      const article = row[0].trim();
      if (article) { articles.push(article); positions.push(i); }
    });
    if (!articles.length) throw new Error('Добавьте артикулы в колонку A');
    if (articles.length > OZ_MAX_ARTICLES) {
      throw new Error('В одном запросе поддерживается не более ' + OZ_MAX_ARTICLES +
        ' SKU. Сейчас: ' + articles.length + '. Разделите список вручную.');
    }

    // Send every SKU in ONE HTTP request. Never clear old prices before success.
    const res = ozonFetch_('/v1/prices', {pvz_url: url, articles: articles});
    if (res.pvz_url !== url || !Array.isArray(res.results) || res.results.length !== articles.length)
      throw new Error('Неверный ответ API: не совпадают ПВЗ или количество артикулов');

    const values = Array.from({length: input.length}, () => ['']);
    let unavailable = 0, errors = 0;
    for (let i = 0; i < articles.length; i++) {
      const item = res.results[i];
      if (String(item.article) !== articles[i])
        throw new Error('Неверный порядок артикулов в ответе');
      const status = String(item.status || '');
      if (status === 'ok' && item.price != null) {
        values[positions[i]] = [item.price];
      } else if (status === 'unavailable' || status === 'no_price') {
        values[positions[i]] = ['Нет данных'];
        unavailable++;
      } else if (['blocked', 'skipped_blocked', 'pvz_error', 'pvz_unverified'].includes(status)) {
        // No partially failed responses overwrite the existing sheet.
        throw new Error('Ozon ограничил доступ или ПВЗ не подтверждён. Попробуйте позже. Статус: ' + status);
      } else {
        // Transient errors are NOT the same as a confirmed unavailable item.
        values[positions[i]] = [''];
        errors++;
      }
    }
    // One write to Sheets after the full response is validated.
    sheet.getRange(2, 2, input.length, 1).setValues(values);
    SpreadsheetApp.getUi().alert('Готово. Получено цен: ' + (articles.length - unavailable - errors) +
      '. Нет данных: ' + unavailable + '. Ошибок: ' + errors + '.');
  } finally {
    lock.releaseLock();
  }
}

function ozonCheckPvz() {
  const sheet = ozonSheet_();
  const url = ozonPvzUrl_(sheet);
  const result = ozonFetch_('/v1/pvz/check', {pvz_url: url});
  SpreadsheetApp.getUi().alert('ПВЗ подтверждён: ' + (result.pvz_address || url));
}