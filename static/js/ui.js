// Small DOM helpers and the option colours.
// All user text goes through text nodes, so a poll option can't inject HTML.

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (key.startsWith('on')) el.addEventListener(key.slice(2), value);
    else if (key === 'class') el.className = value;
    else if (key === 'style') el.style.cssText = value;
    else if (key in el && key !== 'list') el[key] = value;
    else el.setAttribute(key, value === true ? '' : value);
  }
  el.append(...children.flat(Infinity).filter((c) => c !== null && c !== undefined && c !== false));
  return el;
}

// One colour per option, by position in the poll, used on every screen.
const PALETTE = [
  { bg: '#FFC21A', ink: '#2B1C00' },
  { bg: '#2743E8', ink: '#FFFFFF' },
  { bg: '#19C79A', ink: '#04291F' },
  { bg: '#D81E70', ink: '#FFFFFF' },
  { bg: '#25B4F0', ink: '#04263A' },
  { bg: '#6E3BEA', ink: '#FFFFFF' },
  { bg: '#FF7A33', ink: '#2E1000' },
  { bg: '#0E6E6E', ink: '#FFFFFF' },
  { bg: '#A5D321', ink: '#1B2600' },
  { bg: '#8A4B20', ink: '#FFFFFF' },
  { bg: '#FF9EC4', ink: '#3A0A20' },
  { bg: '#3B3F5C', ink: '#FFFFFF' },
];

export const colorFor = (index) => PALETTE[((index % PALETTE.length) + PALETTE.length) % PALETTE.length];

export function optStyle(index) {
  const { bg, ink } = colorFor(index);
  return `--opt:${bg};--opt-ink:${ink}`;
}

let toastTimer;
export function toast(message) {
  const el = document.getElementById('toast');
  el.textContent = message;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 3200);
}

export function listNames(names) {
  if (names.length < 2) return names.join('');
  return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;
}

export const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
