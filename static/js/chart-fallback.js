/* Lightweight local chart fallback used only when Chart.js CDN is unavailable. */
(() => {
  if (window.Chart) return;

  const defaults = { color: '#b9acd2', borderColor: 'rgba(190,126,255,.12)', font: { family: 'system-ui, sans-serif' } };
  const hexToRgba = (value, alpha = 1) => {
    if (typeof value !== 'string') return `rgba(37,137,255,${alpha})`;
    if (value.startsWith('rgba') || value.startsWith('rgb')) return value;
    const hex = value.replace('#', '');
    if (!/^[0-9a-f]{6}$/i.test(hex)) return value;
    const n = parseInt(hex, 16);
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${alpha})`;
  };

  class LocalChart {
    static defaults = defaults;

    constructor(target, config = {}) {
      this.canvas = target?.canvas || target;
      this.ctx = this.canvas?.getContext?.('2d');
      this.config = config;
      this._resize = () => this.draw();
      window.addEventListener('resize', this._resize);
      this.draw();
    }

    destroy() {
      window.removeEventListener('resize', this._resize);
      if (this.ctx && this.canvas) this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    }

    prepare() {
      if (!this.canvas || !this.ctx) return null;
      const box = this.canvas.getBoundingClientRect();
      const ratio = Math.max(1, window.devicePixelRatio || 1);
      const width = Math.max(260, Math.round(box.width || this.canvas.parentElement?.clientWidth || 600));
      const height = Math.max(180, Math.round(box.height || this.canvas.parentElement?.clientHeight || 300));
      this.canvas.width = Math.round(width * ratio);
      this.canvas.height = Math.round(height * ratio);
      this.ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      this.ctx.clearRect(0, 0, width, height);
      this.ctx.font = `11px ${LocalChart.defaults.font.family}`;
      this.ctx.fillStyle = LocalChart.defaults.color;
      return { width, height };
    }

    draw() {
      const size = this.prepare();
      if (!size) return;
      const type = this.config.type || 'bar';
      if (type === 'pie' || type === 'doughnut') this.drawPie(size, type === 'doughnut');
      else if (type === 'line') this.drawLine(size);
      else this.drawBar(size);
    }

    drawAxes(ctx, area, maxValue) {
      ctx.strokeStyle = LocalChart.defaults.borderColor;
      ctx.lineWidth = 1;
      for (let i = 0; i <= 4; i += 1) {
        const y = area.top + (area.height * i) / 4;
        ctx.beginPath(); ctx.moveTo(area.left, y); ctx.lineTo(area.left + area.width, y); ctx.stroke();
        const label = maxValue ? ((maxValue * (4 - i)) / 4).toLocaleString(undefined, { maximumFractionDigits: 1 }) : '0';
        ctx.fillStyle = LocalChart.defaults.color;
        ctx.fillText(label, 4, y + 4);
      }
    }

    drawBar({ width, height }) {
      const ctx = this.ctx;
      const labels = this.config.data?.labels || [];
      const sets = this.config.data?.datasets || [];
      const values = sets.flatMap(s => (s.data || []).map(v => Number(v) || 0));
      const maxValue = Math.max(1, ...values.map(v => Math.abs(v)));
      const area = { left: 52, top: 18, width: width - 68, height: height - 62 };
      this.drawAxes(ctx, area, maxValue);
      const groups = Math.max(1, labels.length);
      const groupWidth = area.width / groups;
      const barWidth = Math.max(3, Math.min(28, (groupWidth * .72) / Math.max(1, sets.length)));
      sets.forEach((set, setIndex) => {
        (set.data || []).forEach((raw, i) => {
          const value = Number(raw) || 0;
          const h = (Math.abs(value) / maxValue) * area.height;
          const x = area.left + i * groupWidth + (groupWidth - barWidth * sets.length) / 2 + setIndex * barWidth;
          const y = area.top + area.height - h;
          const palette = Array.isArray(set.backgroundColor) ? set.backgroundColor : [set.backgroundColor || '#2589ff'];
          ctx.fillStyle = palette[i % palette.length] || '#2589ff';
          ctx.beginPath();
          if (ctx.roundRect) ctx.roundRect(x, y, Math.max(2, barWidth - 2), h, 4); else ctx.rect(x, y, Math.max(2, barWidth - 2), h);
          ctx.fill();
        });
      });
      this.drawLabels(ctx, labels, area, groupWidth);
    }

    drawLine({ width, height }) {
      const ctx = this.ctx;
      const labels = this.config.data?.labels || [];
      const sets = this.config.data?.datasets || [];
      const values = sets.flatMap(s => (s.data || []).map(v => Number(v) || 0));
      const minValue = Math.min(0, ...values);
      const maxValue = Math.max(1, ...values);
      const range = maxValue - minValue || 1;
      const area = { left: 52, top: 18, width: width - 68, height: height - 62 };
      this.drawAxes(ctx, area, maxValue);
      sets.forEach((set, setIndex) => {
        const data = set.data || [];
        const color = set.borderColor || ['#f43f8f', '#2589ff', '#9d4edd', '#08d9d6'][setIndex % 4];
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.beginPath();
        data.forEach((raw, i) => {
          const x = area.left + (data.length <= 1 ? area.width / 2 : (area.width * i) / (data.length - 1));
          const y = area.top + area.height - ((Number(raw || 0) - minValue) / range) * area.height;
          if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        });
        ctx.stroke();
        data.forEach((raw, i) => {
          const x = area.left + (data.length <= 1 ? area.width / 2 : (area.width * i) / (data.length - 1));
          const y = area.top + area.height - ((Number(raw || 0) - minValue) / range) * area.height;
          ctx.fillStyle = color; ctx.beginPath(); ctx.arc(x, y, 2.5, 0, Math.PI * 2); ctx.fill();
        });
      });
      this.drawLabels(ctx, labels, area, labels.length <= 1 ? area.width : area.width / labels.length);
    }

    drawLabels(ctx, labels, area, groupWidth) {
      const maxLabels = Math.max(1, Math.floor(area.width / 70));
      const step = Math.max(1, Math.ceil(labels.length / maxLabels));
      ctx.fillStyle = LocalChart.defaults.color;
      labels.forEach((label, i) => {
        if (i % step !== 0 && i !== labels.length - 1) return;
        const x = area.left + i * groupWidth + groupWidth / 2;
        const text = String(label).slice(0, 12);
        ctx.save(); ctx.translate(x, area.top + area.height + 16); ctx.rotate(-0.25); ctx.textAlign = 'right'; ctx.fillText(text, 0, 0); ctx.restore();
      });
    }

    drawPie({ width, height }, doughnut) {
      const ctx = this.ctx;
      const labels = this.config.data?.labels || [];
      const set = this.config.data?.datasets?.[0] || {};
      const values = (set.data || []).map(v => Math.max(0, Number(v) || 0));
      const total = values.reduce((a, b) => a + b, 0) || 1;
      const colors = Array.isArray(set.backgroundColor) ? set.backgroundColor : ['#2589ff', '#9d4edd', '#f43f8f', '#08d9d6', '#ff7a1a', '#28d982'];
      const legendWidth = width > 520 ? 180 : 0;
      const cx = (width - legendWidth) / 2;
      const cy = height / 2;
      const radius = Math.max(45, Math.min((width - legendWidth) * .34, height * .38));
      let angle = -Math.PI / 2;
      values.forEach((value, i) => {
        const next = angle + (value / total) * Math.PI * 2;
        ctx.beginPath(); ctx.moveTo(cx, cy); ctx.arc(cx, cy, radius, angle, next); ctx.closePath();
        ctx.fillStyle = colors[i % colors.length]; ctx.fill(); angle = next;
      });
      if (doughnut) {
        ctx.beginPath(); ctx.arc(cx, cy, radius * .58, 0, Math.PI * 2); ctx.fillStyle = '#1b0d3d'; ctx.fill();
        ctx.fillStyle = '#fff'; ctx.textAlign = 'center'; ctx.font = `600 12px ${LocalChart.defaults.font.family}`; ctx.fillText(total.toLocaleString(undefined, { maximumFractionDigits: 1 }), cx, cy + 4);
      }
      if (legendWidth) {
        ctx.textAlign = 'left'; ctx.font = `10px ${LocalChart.defaults.font.family}`;
        labels.slice(0, 9).forEach((label, i) => {
          const y = 24 + i * 20; ctx.fillStyle = colors[i % colors.length]; ctx.fillRect(width - legendWidth + 10, y - 8, 9, 9);
          ctx.fillStyle = LocalChart.defaults.color; ctx.fillText(String(label).slice(0, 22), width - legendWidth + 26, y);
        });
      }
    }
  }

  window.Chart = LocalChart;
  console.warn('Chart.js CDN unavailable. Using the local lightweight chart fallback.');
})();
