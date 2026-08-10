(() => {
  const data = window.MIS_DATA || {};
  const quality = window.QUALITY_DATA || {};
  const endpoints = window.MIS_ENDPOINTS || {};
  const palette = ['#2589ff', '#9d4edd', '#f43f8f', '#08d9d6', '#ff7a1a', '#28d982', '#d946ef', '#7c3aed'];

  Chart.defaults.color = '#b9acd2';
  Chart.defaults.borderColor = 'rgba(190,126,255,.12)';
  Chart.defaults.font.family = 'Inter, ui-sans-serif, system-ui, sans-serif';

  const pageMeta = {
    dashboard: ['Dashboard', 'Management overview for the active dataset'],
    upload: ['Upload Center', 'Upload and map a new business dataset'],
    mis: ['MIS Analysis', 'Sales, P&L, products, categories and inventory'],
    quality: ['Data Quality', 'Completeness, duplicates, statistics and correlations'],
    cleaning: ['Data Cleaning', 'Apply reversible cleaning operations'],
    charts: ['Chart Builder', 'Create a custom visual from active data'],
    insights: ['AI Insights', 'Management findings based on calculated KPIs'],
    chat: ['AI Chat', 'Ask questions about the active dataset'],
    reports: ['Reports', 'Download management reports and cleaned data'],
    admin: ['Administration', 'Phase 2 configuration and access management']
  };

  function setSection(name, updateHash = true) {
    if (!document.getElementById(`section-${name}`)) name = 'dashboard';
    document.querySelectorAll('.page-section').forEach(el => el.classList.toggle('active', el.id === `section-${name}`));
    document.querySelectorAll('.nav-item').forEach(el => el.classList.toggle('active', el.dataset.section === name));
    const [title, subtitle] = pageMeta[name] || pageMeta.dashboard;
    document.getElementById('pageTitle').textContent = title;
    document.getElementById('pageSubtitle').textContent = subtitle;
    if (updateHash) history.replaceState(null, '', `#${name}`);
    document.getElementById('sidebar')?.classList.remove('open');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  document.querySelectorAll('[data-section]').forEach(button => {
    button.addEventListener('click', event => {
      const target = event.currentTarget.dataset.section;
      if (target) setSection(target);
    });
  });
  document.getElementById('mobileMenu')?.addEventListener('click', () => document.getElementById('sidebar')?.classList.toggle('open'));
  const initialSection = window.location.hash.replace('#', '') || 'dashboard';
  setSection(initialSection, false);

  document.querySelectorAll('input[type="file"]').forEach(input => {
    input.addEventListener('change', () => {
      const form = input.closest('form');
      const label = form?.querySelector('[data-file-name]');
      if (label) label.textContent = input.files?.length ? `✓ ${input.files[0].name}` : '';
    });
  });

  const commonOptions = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { labels: { boxWidth: 9, usePointStyle: true, font: { size: 9 } } },
      tooltip: { backgroundColor: '#14092f', borderColor: 'rgba(190,126,255,.35)', borderWidth: 1 }
    },
    scales: {
      x: { grid: { display: false }, ticks: { font: { size: 8 }, maxRotation: 35, minRotation: 0 } },
      y: { grid: { color: 'rgba(190,126,255,.09)' }, ticks: { font: { size: 8 } } }
    }
  };

  const trend = data.trend || {};
  const trendLabels = trend.labels?.length ? trend.labels : ['No date trend'];
  const salesTrendCanvas = document.getElementById('salesTrendChart');
  if (salesTrendCanvas) {
    new Chart(salesTrendCanvas, {
      type: 'line',
      data: {
        labels: trendLabels,
        datasets: [
          { label: 'Net Sales', data: trend.net_sales?.length ? trend.net_sales : [0], borderColor: '#f43f8f', backgroundColor: 'rgba(244,63,143,.11)', fill: true, tension: .35, pointRadius: 2 },
          { label: 'Gross Profit', data: trend.gross_profit?.length ? trend.gross_profit : [0], borderColor: '#2589ff', tension: .35, pointRadius: 2 },
          { label: 'EBITDA', data: trend.ebitda?.length ? trend.ebitda : [0], borderColor: '#9d4edd', tension: .35, pointRadius: 2 },
          { label: 'Net Profit', data: trend.net_profit?.length ? trend.net_profit : [0], borderColor: '#08d9d6', tension: .35, pointRadius: 2 }
        ]
      },
      options: commonOptions
    });
  }

  const mixCanvas = document.getElementById('categoryMixChart');
  if (mixCanvas) {
    new Chart(mixCanvas, {
      type: 'doughnut',
      data: { labels: data.mix_labels || [], datasets: [{ data: data.mix_values || [], backgroundColor: palette, borderColor: '#201046', borderWidth: 3 }] },
      options: { responsive: true, maintainAspectRatio: false, cutout: '64%', plugins: { legend: { position: 'right', labels: { boxWidth: 8, usePointStyle: true, font: { size: 8 } } } } }
    });
  }

  const pnlCanvas = document.getElementById('pnlChart');
  if (pnlCanvas && data.pnl) {
    new Chart(pnlCanvas, {
      type: 'bar',
      data: {
        labels: ['Gross Sales', 'Net Sales', 'COGS', 'Gross Profit', 'OpEx', 'EBITDA', 'Net Profit'],
        datasets: [{
          label: 'Amount',
          data: [data.pnl.gross_sales, data.pnl.net_sales, data.pnl.cogs, data.pnl.gross_profit, data.pnl.opex, data.pnl.ebitda, data.pnl.net_profit],
          backgroundColor: ['#f43f8f', '#2589ff', '#ff5364', '#9d4edd', '#ff7a1a', '#08d9d6', '#28d982'],
          borderRadius: 6
        }]
      },
      options: { ...commonOptions, plugins: { ...commonOptions.plugins, legend: { display: false } } }
    });
  }

  const inventoryCanvas = document.getElementById('inventoryChart');
  if (inventoryCanvas) {
    const products = (data.top_products || []).filter(p => Number.isFinite(Number(p.stock_qty))).slice(0, 8);
    new Chart(inventoryCanvas, {
      type: 'bar',
      data: {
        labels: products.length ? products.map(p => p.product) : ['No stock data'],
        datasets: [{ label: 'Stock Qty', data: products.length ? products.map(p => p.stock_qty) : [0], backgroundColor: palette, borderRadius: 5 }]
      },
      options: { ...commonOptions, plugins: { ...commonOptions.plugins, legend: { display: false } } }
    });
  }

  const missingCanvas = document.getElementById('missingChart');
  if (missingCanvas) {
    const missing = quality.missing_columns || [];
    new Chart(missingCanvas, {
      type: 'bar',
      data: {
        labels: missing.length ? missing.map(item => item.column) : ['No missing values'],
        datasets: [{ label: 'Missing Values', data: missing.length ? missing.map(item => item.missing) : [0], backgroundColor: 'rgba(244,63,143,.72)', borderColor: '#f43f8f', borderWidth: 1, borderRadius: 5 }]
      },
      options: { ...commonOptions, plugins: { ...commonOptions.plugins, legend: { display: false } } }
    });
  }

  function renderCorrelation() {
    const target = document.getElementById('correlationGrid');
    if (!target) return;
    const labels = quality.correlation_labels || [];
    const values = quality.correlation_values || [];
    target.textContent = '';
    if (!labels.length) {
      target.innerHTML = '<div class="empty-state">At least two numeric columns are required.</div>';
      return;
    }
    const columns = labels.length + 1;
    const header = document.createElement('div');
    header.className = 'corr-row';
    header.style.gridTemplateColumns = `110px repeat(${labels.length}, minmax(48px, 1fr))`;
    header.appendChild(Object.assign(document.createElement('div'), { className: 'corr-cell corr-label' }));
    labels.forEach(label => {
      const cell = document.createElement('div'); cell.className = 'corr-cell corr-label'; cell.textContent = label; header.appendChild(cell);
    });
    target.appendChild(header);
    values.forEach((row, i) => {
      const line = document.createElement('div');
      line.className = 'corr-row';
      line.style.gridTemplateColumns = `110px repeat(${labels.length}, minmax(48px, 1fr))`;
      const rowLabel = document.createElement('div'); rowLabel.className = 'corr-cell corr-label'; rowLabel.textContent = labels[i]; line.appendChild(rowLabel);
      row.forEach(value => {
        const cell = document.createElement('div');
        cell.className = 'corr-cell';
        const numeric = Number(value || 0);
        const alpha = Math.min(.78, .12 + Math.abs(numeric) * .66);
        cell.style.background = numeric >= 0 ? `rgba(37,137,255,${alpha})` : `rgba(244,63,143,${alpha})`;
        cell.textContent = value == null ? '—' : Number(value).toFixed(2);
        line.appendChild(cell);
      });
      target.appendChild(line);
    });
    target.style.setProperty('--corr-columns', columns);
  }
  renderCorrelation();

  async function fetchInsights() {
    const status = document.getElementById('insightsStatus');
    const output = document.getElementById('insightsOutput');
    const buttons = [document.getElementById('generateInsightsBtn'), document.getElementById('quickInsightsBtn')].filter(Boolean);
    buttons.forEach(button => { button.disabled = true; });
    if (status) status.textContent = 'Analysing calculated KPIs and data-quality signals...';
    try {
      const response = await fetch(endpoints.insights, { method: 'POST' });
      const result = await response.json();
      if (!result.ok) throw new Error(result.error || 'Could not generate insights.');
      if (output) output.textContent = result.text;
      if (status) status.textContent = `Generated using ${result.source}.`;
      setSection('insights');
    } catch (error) {
      if (status) status.textContent = error.message;
    } finally {
      buttons.forEach(button => { button.disabled = false; });
    }
  }
  document.getElementById('generateInsightsBtn')?.addEventListener('click', fetchInsights);
  document.getElementById('quickInsightsBtn')?.addEventListener('click', fetchInsights);

  const chatLog = document.getElementById('chatLog');
  const chatInput = document.getElementById('chatInput');
  const chatStatus = document.getElementById('chatStatus');
  function appendChat(text, role) {
    if (!chatLog) return;
    const message = document.createElement('div');
    message.className = `chat-message ${role}`;
    message.textContent = text;
    chatLog.appendChild(message);
    chatLog.scrollTop = chatLog.scrollHeight;
  }
  async function askQuestion(question) {
    const clean = String(question || '').trim();
    if (!clean) return;
    setSection('chat');
    appendChat(clean, 'user');
    if (chatInput) chatInput.value = '';
    if (chatStatus) chatStatus.textContent = 'Calculating answer...';
    document.getElementById('sendChatBtn').disabled = true;
    try {
      const response = await fetch(endpoints.chat, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question: clean })
      });
      const result = await response.json();
      if (!result.ok) throw new Error(result.error || result.answer || 'Could not answer the question.');
      appendChat(result.answer, 'assistant');
      if (chatStatus) chatStatus.textContent = `Answer source: ${result.source}.`;
    } catch (error) {
      appendChat(error.message, 'assistant');
      if (chatStatus) chatStatus.textContent = 'Question failed.';
    } finally {
      document.getElementById('sendChatBtn').disabled = false;
    }
  }
  document.getElementById('sendChatBtn')?.addEventListener('click', () => askQuestion(chatInput?.value));
  chatInput?.addEventListener('keydown', event => { if (event.key === 'Enter') askQuestion(chatInput.value); });
  document.querySelectorAll('.chat-question, .quick-question').forEach(button => button.addEventListener('click', () => askQuestion(button.textContent)));

  let customChart = null;
  async function buildCustomChart() {
    const button = document.getElementById('buildChartBtn');
    const status = document.getElementById('chartBuilderStatus');
    button.disabled = true;
    status.textContent = 'Preparing chart data...';
    try {
      const payload = {
        x: document.getElementById('chartX').value,
        y: document.getElementById('chartY').value,
        aggregation: document.getElementById('chartAgg').value
      };
      const response = await fetch(endpoints.chart, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      const result = await response.json();
      if (!result.ok) throw new Error(result.error || 'Could not build chart.');
      customChart?.destroy();
      const chartType = document.getElementById('chartType').value;
      customChart = new Chart(document.getElementById('customChart'), {
        type: chartType,
        data: { labels: result.labels, datasets: [{ label: result.y_label, data: result.values, backgroundColor: chartType === 'line' ? 'rgba(244,63,143,.12)' : palette, borderColor: chartType === 'line' ? '#f43f8f' : palette, borderWidth: 2, tension: .3, fill: chartType === 'line', borderRadius: 5 }] },
        options: ['pie', 'doughnut'].includes(chartType)
          ? { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right', labels: { boxWidth: 8, font: { size: 9 } } } } }
          : commonOptions
      });
      status.textContent = `Showing ${result.y_label} by ${result.x_label}.`;
    } catch (error) {
      status.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  }
  document.getElementById('buildChartBtn')?.addEventListener('click', buildCustomChart);
})();
