// Canvas spin wheel. The server chooses the result; this only draws it, so the
// same slices and jitter end at the same resting position on every phone.
import { colorFor } from './ui.js';

const TAU = Math.PI * 2;
const DURATION = 5000;
const easeOut = (t) => 1 - (1 - t) ** 4;

export class Wheel {
  constructor(canvas, { colorIndex, onTick }) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.colorIndex = colorIndex; // option id -> position in the poll, for stable colours
    this.onTick = onTick;
    this.slices = [];
    this.rotation = 0;
    this.highlight = null;
    this.size = 0;
    new ResizeObserver(() => this.resize()).observe(canvas);
  }

  resize() {
    const size = this.canvas.clientWidth;
    if (!size) return;
    const ratio = window.devicePixelRatio || 1;
    this.canvas.width = size * ratio;
    this.canvas.height = size * ratio;
    this.ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    this.size = size;
    this.draw();
  }

  setSlices(slices) {
    const total = slices.reduce((sum, s) => sum + s.weight, 0);
    let start = 0;
    this.slices = slices.map((slice) => {
      const span = (slice.weight / total) * TAU;
      const item = { ...slice, start, end: start + span };
      start += span;
      return item;
    });
    this.highlight = null;
    this.draw();
  }

  draw() {
    const { ctx, size } = this;
    if (!size) return;
    const radius = size / 2 - 2;
    const middle = size / 2;
    ctx.clearRect(0, 0, size, size);
    ctx.save();
    ctx.translate(middle, middle);
    ctx.rotate(this.rotation - Math.PI / 2); // angle 0 sits at the pointer

    for (const slice of this.slices) {
      const { bg, ink } = colorFor(this.colorIndex(slice.id));
      ctx.globalAlpha = this.highlight && this.highlight !== slice.id ? 0.25 : 1;
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.arc(0, 0, radius, slice.start, slice.end);
      ctx.closePath();
      ctx.fillStyle = bg;
      ctx.fill();
      this.drawLabel(slice, radius, ink);
    }
    ctx.restore();
  }

  drawLabel(slice, radius, ink) {
    const { ctx } = this;
    const span = slice.end - slice.start;
    const fontSize = Math.max(13, Math.min(radius * 0.105, 20));
    if (span * radius * 0.72 < fontSize * 1.05) return; // too thin to read
    ctx.save();
    const middle = slice.start + span / 2;
    ctx.rotate(middle);
    // Labels on the left half would read upside down, so turn them over.
    const flipped = Math.cos(middle + this.rotation - Math.PI / 2) < 0;
    if (flipped) ctx.rotate(Math.PI);
    ctx.textAlign = flipped ? 'left' : 'right';
    ctx.textBaseline = 'middle';
    ctx.font = `650 ${fontSize}px "Bricolage Grotesque", system-ui, sans-serif`;
    ctx.fillStyle = ink;
    const room = radius * 0.66;
    let text = slice.label;
    if (ctx.measureText(text).width > room) {
      while (text.length > 1 && ctx.measureText(`${text}…`).width > room) text = text.slice(0, -1);
      text = `${text.trimEnd()}…`;
    }
    ctx.fillText(text, flipped ? -(radius - 14) : radius - 14, 0);
    ctx.restore();
  }

  restingRotation(landedId, jitter) {
    const slice = this.slices.find((s) => s.id === landedId);
    if (!slice) return 0;
    // Stay clear of the slice edges so the result is never ambiguous.
    const target = slice.start + (0.12 + 0.76 * jitter) * (slice.end - slice.start);
    return ((-target % TAU) + TAU) % TAU;
  }

  showResult(landedId, jitter) {
    this.rotation = this.restingRotation(landedId, jitter);
    this.highlight = landedId;
    this.draw();
  }

  sliceAtPointer(rotation) {
    const angle = ((-rotation % TAU) + TAU) % TAU;
    return this.slices.findIndex((s) => angle >= s.start && angle < s.end);
  }

  spinTo(landedId, jitter) {
    this.highlight = null;
    const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduced) {
      this.showResult(landedId, jitter);
      return Promise.resolve();
    }

    const from = this.rotation % TAU;
    const rest = this.restingRotation(landedId, jitter);
    const to = rest + TAU * 6 + (rest < from ? TAU : 0);
    const startedAt = performance.now();
    let lastSlice = this.sliceAtPointer(from);

    return new Promise((resolve) => {
      const frame = (now) => {
        const t = Math.min(1, (now - startedAt) / DURATION);
        this.rotation = from + (to - from) * easeOut(t);
        this.draw();
        const current = this.sliceAtPointer(this.rotation);
        if (current !== lastSlice) {
          lastSlice = current;
          this.onTick?.();
        }
        if (t < 1) {
          requestAnimationFrame(frame);
        } else {
          this.showResult(landedId, jitter);
          resolve();
        }
      };
      requestAnimationFrame(frame);
    });
  }
}
