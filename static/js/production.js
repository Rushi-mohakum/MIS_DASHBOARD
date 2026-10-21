(() => {
  const data = window.PRODUCTION_DATA || {};
  const kpi = data.kpi || {};
  const palette = {
    cyan: '#22e4dc',
    green: '#13d7a0',
    blue: '#3295ff',
    red: '#ff4d72',
    amber: '#ffb547',
    violet: '#9e7bff',
    muted: '#7199a3'
  };
  const charts = [];

  const sidebar = document.getElementById('prodSidebar');
  document.getElementById('prodMobileMenu')?.addEventListener('click', () => sidebar?.classList.toggle('open'));
  document.addEventListener('click', event => {
    if (sidebar?.classList.contains('open') && !sidebar.contains(event.target) && !event.target.closest('#prodMobileMenu')) {
      sidebar.classList.remove('open');
    }
  });

  const fileInput = document.getElementById('prodEmptyFile');
  fileInput?.addEventListener('change', () => {
    const picked = document.getElementById('prodPickedFile');
    if (picked) picked.textContent = fileInput.files?.length ? `Selected: ${fileInput.files[0].name}` : 'No file selected';
  });

  function activatePanel(name) {
    document.querySelectorAll('[data-prod-tab]').forEach(tab => tab.classList.toggle('active', tab.dataset.prodTab === name));
    document.querySelectorAll('[data-prod-panel]').forEach(panel => panel.classList.toggle('active', panel.dataset.prodPanel === name));
    sidebar?.classList.remove('open');
    charts.forEach(chart => {
      try { chart.resize(); } catch (_) {}
    });
  }
  document.querySelectorAll('[data-prod-tab]').forEach(tab => {
    tab.addEventListener('click', () => activatePanel(tab.dataset.prodTab));
  });
  document.querySelectorAll('[data-prod-open]').forEach(button => {
    button.addEventListener('click', () => {
      activatePanel(button.dataset.prodOpen);
      document.querySelector(`[data-prod-panel="${button.dataset.prodOpen}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });

  if (typeof Chart === 'undefined' || !data.ok) return;

  Chart.defaults.color = '#8db2bc';
  Chart.defaults.borderColor = 'rgba(91, 177, 188, .11)';
  Chart.defaults.font.family = "'DM Sans', Inter, system-ui, sans-serif";
  Chart.defaults.font.size = 9;

  const shortNum = value => {
    const n = Number(value) || 0;
    const abs = Math.abs(n);
    if (abs >= 1e7) return `${(n / 1e7).toFixed(1)}Cr`;
    if (abs >= 1e5) return `${(n / 1e5).toFixed(1)}L`;
    if (abs >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
    return Math.round(n).toLocaleString('en-IN');
  };
  const commonOptions = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: {
        position: 'bottom',
        labels: { color: '#8fb4be', boxWidth: 7, boxHeight: 7, usePointStyle: true, pointStyle: 'circle', padding: 14, font: { size: 8 } }
      },
      tooltip: {
        backgroundColor: '#06262f',
        borderColor: 'rgba(34,228,220,.28)',
        borderWidth: 1,
        titleColor: '#f1ffff',
        bodyColor: '#b5d0d6',
        padding: 10,
        displayColors: true
      }
    },
    scales: {
      x: {
        grid: { display: false },
        ticks: { color: '#7299a4', font: { size: 8 }, maxRotation: 35, minRotation: 0 },
        border: { display: false }
      },
      y: {
        grid: { color: 'rgba(91,177,188,.1)' },
        ticks: { color: '#7299a4', font: { size: 8 }, callback: value => shortNum(value) },
        border: { display: false }
      }
    }
  };

  function chart(id, type, labels, datasets, options = {}) {
    const canvas = document.getElementById(id);
    if (!canvas) return null;
    const instance = new Chart(canvas, {
      type,
      data: { labels: labels || [], datasets: datasets || [] },
      options: {
        ...commonOptions,
        ...options,
        plugins: { ...commonOptions.plugins, ...(options.plugins || {}) },
        scales: options.scales ? options.scales : commonOptions.scales
      }
    });
    charts.push(instance);
    return instance;
  }
  const ds = (label, values, color, extra = {}) => ({
    label, data: values || [], borderColor: color, backgroundColor: color,
    borderWidth: 2, borderRadius: 5, maxBarThickness: 25, pointRadius: 2,
    pointHoverRadius: 4, tension: .32, ...extra
  });
  const trend = data.trend || {};
  const plant = data.plant || {};
  const machines = data.machines || [];
  const defects = data.defects || [];
  const shifts = data.shift || {};
  const operators = data.operators || [];
  const energy = data.energy || {};

  chart('overviewTrend', 'line', trend.labels, [
    ds('Total production', trend.total, palette.blue, { fill: true, backgroundColor: 'rgba(50,149,255,.08)' }),
    ds('OK production', trend.ok, palette.green),
    ds('Rejected', trend.rejected, palette.red, { borderDash: [4, 3] })
  ]);
  chart('overviewPlant', 'bar', plant.labels, [
    ds('OK production', plant.ok, palette.green),
    ds('Rejected', plant.rejected, palette.red)
  ], { scales: { ...commonOptions.scales, x: { ...commonOptions.scales.x, ticks: { ...commonOptions.scales.x.ticks, maxRotation: 0 } } } });
  chart('overviewTarget', 'bar', plant.labels, [
    ds('Target', plant.target, 'rgba(130,177,190,.42)', { borderColor: '#8bb9c4', borderWidth: 1 }),
    ds('Actual', plant.total, palette.blue)
  ]);
  chart('overviewMachines', 'bar', machines.slice(0, 7).map(item => item.machine), [
    ds('Total production', machines.slice(0, 7).map(item => item.total), palette.blue)
  ], {
    indexAxis: 'y',
    scales: {
      x: { grid: { color: 'rgba(91,177,188,.1)' }, ticks: { color: '#7299a4', font: { size: 8 }, callback: shortNum }, border: { display: false } },
      y: { grid: { display: false }, ticks: { color: '#9bbdc5', font: { size: 8 } }, border: { display: false } }
    },
    plugins: { legend: { display: false } }
  });
  chart('overviewDefects', 'bar', defects.slice(0, 6).map(item => item.defect), [
    ds('Defect quantity', defects.slice(0, 6).map(item => item.qty), palette.red)
  ], {
    indexAxis: 'y',
    scales: {
      x: { grid: { color: 'rgba(91,177,188,.1)' }, ticks: { color: '#7299a4', font: { size: 8 }, callback: shortNum }, border: { display: false } },
      y: { grid: { display: false }, ticks: { color: '#9bbdc5', font: { size: 8 } }, border: { display: false } }
    },
    plugins: { legend: { display: false } }
  });
  chart('overviewOee', 'bar', plant.labels, [
    ds('OEE %', plant.oee, palette.violet, { backgroundColor: 'rgba(158,123,255,.78)' })
  ], {
    scales: {
      x: { grid: { display: false }, ticks: { color: '#7299a4', font: { size: 8 } }, border: { display: false },
      },
      y: { min: 0, max: 100, grid: { color: 'rgba(91,177,188,.1)' }, ticks: { color: '#7299a4', font: { size: 8 }, callback: value => `${value}%` }, border: { display: false } }
    },
    plugins: { legend: { display: false } }
  });
  chart('overviewShift', 'bar', shifts.labels, [
    ds('Production', shifts.total, palette.amber)
  ], { plugins: { legend: { display: false } } });
  chart('overviewMaterial', 'bar', ['Material'], [
    ds('Actual used', [data.metric_status?.material ? kpi.material_used : null], palette.green),
    ds('Required', [data.metric_status?.material ? kpi.material_required : null], palette.blue)
  ], { plugins: { legend: { position: 'bottom' } }, scales: { ...commonOptions.scales, x: { ...commonOptions.scales.x, ticks: { display: false } } } });

  chart('plantDetailChart', 'bar', plant.labels, [
    ds('Total production', plant.total, palette.blue),
    ds('OK production', plant.ok, palette.green),
    ds('Target', plant.target, 'rgba(255,181,71,.75)')
  ]);
  chart('plantOeeDetailChart', 'bar', plant.labels, [
    ds('OEE %', plant.oee, palette.violet)
  ], {
    scales: {
      x: commonOptions.scales.x,
      y: { min: 0, max: 100, grid: { color: 'rgba(91,177,188,.1)' }, ticks: { color: '#7299a4', font: { size: 8 }, callback: value => `${value}%` }, border: { display: false } }
    },
    plugins: { legend: { display: false } }
  });
  chart('qualityDefectChart', 'bar', defects.map(item => item.defect), [
    ds('Defect quantity', defects.map(item => item.qty), palette.red)
  ], {
    indexAxis: 'y',
    scales: {
      x: { grid: { color: 'rgba(91,177,188,.1)' }, ticks: { color: '#7299a4', font: { size: 8 }, callback: shortNum }, border: { display: false } },
      y: { grid: { display: false }, ticks: { color: '#9bbdc5', font: { size: 8 } }, border: { display: false } }
    },
    plugins: { legend: { display: false } }
  });
  chart('qualityProductChart', 'bar', (data.pareto_products || []).map(item => item.product), [
    ds('Production', (data.pareto_products || []).map(item => item.production), palette.blue),
    ds('Rejected', (data.pareto_products || []).map(item => item.rejected), palette.red)
  ]);
  chart('workforceEfficiencyChart', 'bar', operators.map(item => item.operator), [
    ds('Efficiency %', operators.map(item => item.efficiency_pct), palette.green)
  ], {
    indexAxis: 'y',
    scales: {
      x: { min: 0, max: 150, grid: { color: 'rgba(91,177,188,.1)' }, ticks: { color: '#7299a4', font: { size: 8 }, callback: value => `${value}%` }, border: { display: false } },
      y: { grid: { display: false }, ticks: { color: '#9bbdc5', font: { size: 8 } }, border: { display: false } }
    },
    plugins: { legend: { display: false } }
  });
  chart('planningTargetChart', 'bar', plant.labels, [
    ds('Target', plant.target, 'rgba(255,181,71,.72)'),
    ds('Actual', plant.total, palette.blue)
  ]);
  chart('planningMaterialChart', 'bar', ['Material'], [
    ds('Actual used', [data.metric_status?.material ? kpi.material_used : null], palette.green),
    ds('Required', [data.metric_status?.material ? kpi.material_required : null], palette.blue)
  ], { plugins: { legend: { position: 'bottom' } }, scales: { ...commonOptions.scales, x: { ...commonOptions.scales.x, ticks: { display: false } } } });
  chart('energyDowntimeChart', 'bar', (data.downtime || []).map(item => item.reason), [
    ds('Minutes', (data.downtime || []).map(item => item.minutes), palette.amber)
  ], {
    indexAxis: 'y',
    scales: {
      x: { grid: { color: 'rgba(91,177,188,.1)' }, ticks: { color: '#7299a4', font: { size: 8 }, callback: shortNum }, border: { display: false } },
      y: { grid: { display: false }, ticks: { color: '#9bbdc5', font: { size: 8 } }, border: { display: false } }
    },
    plugins: { legend: { display: false } }
  });
  chart('energyUsageChart', 'line', energy.labels || [], [
    ds('Used units', energy.usage || [], palette.cyan, { fill: true, backgroundColor: 'rgba(34,228,220,.08)' })
  ], { plugins: { legend: { display: false } } });
})();