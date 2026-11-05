// Everything that touches Telegram.WebApp lives here. Outside Telegram each call
// falls back to a browser equivalent, so the app can be tested in a normal tab.
const W = window.Telegram?.WebApp;
export const inTelegram = Boolean(W?.initData);
const supports = (version) => inTelegram && W.isVersionAtLeast(version);
const params = new URLSearchParams(location.search);

export function setup() {
  if (!inTelegram) return;
  W.ready();
  W.expand();
  if (supports('7.7')) W.disableVerticalSwipes(); // keeps card drags from closing the app
  const applyTheme = () => { document.documentElement.dataset.theme = W.colorScheme; };
  applyTheme();
  W.onEvent('themeChanged', applyTheme);
}

export const initData = () => (inTelegram ? W.initData : '');
export const devUser = () => params.get('as') || 'Tester';
export const devChat = () => params.get('chat') || '';

// start_param is only used to choose a screen. Identity always comes from the
// signed initData, which the server checks.
export function startParam() {
  return W?.initDataUnsafe?.start_param
    || params.get('tgWebAppStartParam')
    || params.get('startapp')
    || '';
}

/* Main button: Telegram's BottomButton, or a fixed bar in a browser. */
const bar = document.getElementById('main-bar');
const domButton = document.getElementById('main-button');
let mainHandler = null;

function runMain() { mainHandler?.(); }
domButton.addEventListener('click', runMain);
if (inTelegram) W.MainButton.onClick(runMain);

export function setMain(text, handler, { active = true } = {}) {
  mainHandler = handler;
  if (inTelegram) {
    W.MainButton.setParams({ text, is_active: active, is_visible: true });
    return;
  }
  bar.hidden = false;
  document.body.classList.add('has-fallback-main');
  domButton.textContent = text;
  domButton.disabled = !active;
}

export function hideMain() {
  mainHandler = null;
  if (inTelegram) { W.MainButton.hide(); return; }
  bar.hidden = true;
  document.body.classList.remove('has-fallback-main');
}

export function setMainBusy(busy) {
  if (inTelegram) {
    if (busy) W.MainButton.showProgress(false); else W.MainButton.hideProgress();
  } else {
    domButton.disabled = busy;
  }
}

/* Back button */
let backHandler = null;
if (inTelegram && supports('6.1')) W.BackButton.onClick(() => backHandler?.());

export const hasNativeBack = () => supports('6.1');

export function setBack(handler) {
  backHandler = handler;
  if (!supports('6.1')) return;
  if (handler) W.BackButton.show(); else W.BackButton.hide();
}

/* Haptics */
export const haptic = {
  tick() { if (supports('6.1')) W.HapticFeedback.selectionChanged(); },
  tap() { if (supports('6.1')) W.HapticFeedback.impactOccurred('light'); },
  win() { if (supports('6.1')) W.HapticFeedback.notificationOccurred('success'); },
  warn() { if (supports('6.1')) W.HapticFeedback.notificationOccurred('warning'); },
};

/* Sharing */
export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const area = document.createElement('textarea');
    area.value = text;
    document.body.append(area);
    area.select();
    const ok = document.execCommand('copy');
    area.remove();
    return ok;
  }
}

// Plain share sheet: works everywhere, and sends the link as ordinary text.
export function shareLink(url, text) {
  const share = `https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(text)}`;
  if (inTelegram) { W.openTelegramLink(share); return 'opened'; }
  return null;
}

// Rich share: a card with an open button, prepared by the bot (Bot API 8.0+).
export function shareRich(preparedId) {
  return new Promise((resolve) => {
    if (!supports('8.0')) { resolve(false); return; }
    W.shareMessage(preparedId, (sent) => resolve(Boolean(sent)));
  });
}

export const canShareRich = () => supports('8.0');
