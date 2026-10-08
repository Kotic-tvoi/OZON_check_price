/**
 * Google Таблица -> Ozon price reader (read-only).
 * A: Артикул товара. B: Конечная цена.
 * H2: ОДНА ссылка на ПВЗ для всех SKU в выбранном запуске.
 * Только ручной запуск из меню. Без триггеров и сохранения цен на сервере.
 */
const OZ_SHEET_NAME = 'Цены Ozon';
const OZ_BATCH = 8; // Один browser session на пакет; уменьшите при таймаутах.
const OZ_MAX_RUNTIME_MS = 230000;
const OZ_CURSOR = 'OZON_PRICE_NEXT_ROW';
const OZ_RUN_PVZ = 'OZON_PRICE_RUN_PVZ';
const OZ_ERRORS = 'OZON_PRICE_ERRORS';
const OZ_PROCESSED = 'OZON_PRICE_PROCESSED';
const OZ_PVZ_CELL = 'H2';
const OZ_DEFAULT_PVZ = 'https://www.ozon.ru/geo/moskva/442329/';

function onOpen() {
  SpreadsheetApp.getUi().createMenu('Ozon — цены')
    .addItem('Настроить подключение', 'ozonConfigure')
    .addItem('Обновить все цены', 'ozonStart')
    .addItem('Продолжить обновление', 'ozonContinue')
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
    throw new Error('Обнаружена старая структура, где ПВЗ записан в каждой строке. ' +
      'Сделайте копию листа и перенесите артикулы в A, освободив B для цен. ПВЗ теперь указывается один раз в H2.');
  }
  // Убираем ТОЛЬКО старые технические колонки нашей предыдущей версии.
  if (sheet.getRange('C1').getDisplayValue() === 'Тип цены' &&
      sheet.getRange('D1').getDisplayValue() === 'Статус') {
    sheet.getRange(1, 3, sheet.getLastRow(), 4).clearContent();
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
  if (!/^https:\/\/(?:www\.)?ozon\.ru\/geo\/[a-z0-9-]+\/\d+\/?$/i.test(url))
    throw new Error('Укажите полную ссылку на ПВЗ Ozon в ячейке ' + OZ_PVZ_CELL);
  const matched = url.match(/^https:\/\/(?:www\.)?ozon\.ru\/geo\/([a-z0-9-]+)\/(\d+)\/?$/i);
  return 'https://www.ozon.ru/geo/' + matched[1].toLowerCase() + '/' + matched[2] + '/';
}

function ozonFetch_(path, payload) {
  const props = PropertiesService.getScriptProperties();
  const base = props.getProperty('OZON_SERVER_URL');
  const token = props.getProperty('OZON_API_TOKEN');
  if (!base || !token) throw new Error('Сначала выберите: Ozon — цены → Настроить подключение');
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
    const props = PropertiesService.getScriptProperties();
    if (!props.getProperty('OZON_SERVER_URL') || !props.getProperty('OZON_API_TOKEN'))
      throw new Error('Сначала настройте подключение к Python-сервису');
    const doc = PropertiesService.getDocumentProperties();
    const lastRow = sheet.getLastRow();
    if (lastRow > 1) sheet.getRange(2, 2, lastRow - 1, 1).clearContent();
    doc.setProperties({[OZ_CURSOR]: '2', [OZ_RUN_PVZ]: url,
      [OZ_ERRORS]: '0', [OZ_PROCESSED]: '0'});
  } finally { lock.releaseLock(); }
  ozonContinue();
}

function ozonContinue() {
  const lock = LockService.getDocumentLock();
  if (!lock.tryLock(1000)) throw new Error('Обновление уже запущено в другом окне');
  try {
    const sheet = ozonSheet_();
    const url = ozonPvzUrl_(sheet);
    const doc = PropertiesService.getDocumentProperties();
    const originalPvz = doc.getProperty(OZ_RUN_PVZ);
    if (originalPvz && originalPvz !== url)
      throw new Error('ПВЗ изменился во время сбора. Нажмите «Обновить все цены» для нового ПВЗ.');
    if (!originalPvz) doc.setProperty(OZ_RUN_PVZ, url);
    const lastRow = sheet.getLastRow();
    if (lastRow < 2) { SpreadsheetApp.getUi().alert('Добавьте SKU в колонку A'); return; }
    let nextRow = Math.max(2, Number(doc.getProperty(OZ_CURSOR) || 2));
    const started = Date.now();
    let errors = Number(doc.getProperty(OZ_ERRORS) || 0);
    let processed = Number(doc.getProperty(OZ_PROCESSED) || 0);
    while (nextRow <= lastRow && Date.now() - started < OZ_MAX_RUNTIME_MS) {
      const count = Math.min(OZ_BATCH, lastRow - nextRow + 1);
      const input = sheet.getRange(nextRow, 1, count, 1).getDisplayValues();
      const articles = [], positions = [];
      for (let i = 0; i < count; i++) {
        const sku = input[i][0].trim();
        if (sku) { articles.push(sku); positions.push(i); }
      }
      const values = Array.from({length: count}, () => ['']);
      if (articles.length) {
        // Один pvz_url на весь пакет — НЕ по одному URL на SKU.
        const res = ozonFetch_('/v1/prices', {pvz_url: url, articles: articles});
        if (res.pvz_url !== url || !Array.isArray(res.results) || res.results.length !== articles.length)
          throw new Error('Неверный ответ API: ПВЗ или количество артикулов не совпадают');
        for (let j = 0; j < res.results.length; j++) {
          const item = res.results[j];
          if (String(item.article) !== articles[j])
            throw new Error('Нарушен исходный порядок артикулов в ответе API');
          if (item.price != null && /^ok/.test(item.status || '')) {
            values[positions[j]] = [item.price];
          } else { errors++; }
        }
        processed += articles.length;
      }
      // Если цена не получена, ячейка остаётся пустой, старая цена не сохраняется.
      sheet.getRange(nextRow, 2, count, 1).setValues(values);
      nextRow += count;
      doc.setProperties({[OZ_CURSOR]: String(nextRow), [OZ_ERRORS]: String(errors),
        [OZ_PROCESSED]: String(processed)});
      SpreadsheetApp.flush();
    }
    if (nextRow > lastRow) {
      doc.deleteProperty(OZ_CURSOR); doc.deleteProperty(OZ_RUN_PVZ);
      doc.deleteProperty(OZ_ERRORS); doc.deleteProperty(OZ_PROCESSED);
      SpreadsheetApp.getUi().alert('Готово. Проверено SKU: ' + processed +
        '. Не удалось получить цены: ' + errors + '.');
    } else {
      SpreadsheetApp.getUi().alert('Проверено SKU: ' + processed +
        '. Осталось продолжить обновление через меню.');
    }
  } finally { lock.releaseLock(); }
}

function ozonCheckPvz() {
  const sheet = ozonSheet_();
  const url = ozonPvzUrl_(sheet);
  const result = ozonFetch_('/v1/pvz/check', {pvz_url: url});
  SpreadsheetApp.getUi().alert('ПВЗ подтверждён: ' + (result.pvz_address || url));
}