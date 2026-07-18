const REFRESH_MS = 60_000;

function fmtMoney(v) {
  const sign = v < 0 ? '-' : '';
  return sign + '$' + Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtPct(v, digits = 3) {
  const sign = v > 0 ? '+' : '';
  return sign + v.toFixed(digits) + '%';
}

function fmtTime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

async function fetchJSON(path) {
  const res = await fetch(path + '?_=' + Date.now());
  if (!res.ok) throw new Error('Failed to fetch ' + path);
  return res.json();
}

let priceChart, equityChart;

function buildTradeMarkers(trades) {
  const entries = [], exits = [];
  for (const t of trades) {
    entries.push({ x: new Date(t.entry_time).getTime(), y: t.entry_price, dir: t.direction });
    exits.push({ x: new Date(t.exit_time).getTime(), y: t.exit_price, pnl: t.pnl });
  }
  return { entries, exits };
}

function renderPriceChart(priceHistory, trades) {
  const points = priceHistory.map(p => ({ x: new Date(p.t).getTime(), y: p.c }));
  const { entries, exits } = buildTradeMarkers(trades);

  const longEntries = entries.filter(e => e.dir === 'long');
  const shortEntries = entries.filter(e => e.dir === 'short');

  const ctx = document.getElementById('priceChart').getContext('2d');
  if (priceChart) priceChart.destroy();
  priceChart = new Chart(ctx, {
    type: 'line',
    data: {
      datasets: [
        {
          label: 'AUD/USD',
          data: points,
          borderColor: '#4d9dff',
          backgroundColor: 'rgba(77,157,255,0.08)',
          borderWidth: 1.6,
          pointRadius: 0,
          fill: true,
          tension: 0.15,
          order: 3,
        },
        {
          label: 'Long Entry',
          data: longEntries,
          type: 'scatter',
          pointStyle: 'triangle',
          pointRadius: 7,
          backgroundColor: '#26d97a',
          borderColor: '#26d97a',
          order: 1,
        },
        {
          label: 'Short Entry',
          data: shortEntries,
          type: 'scatter',
          pointStyle: 'triangle',
          rotation: 180,
          pointRadius: 7,
          backgroundColor: '#ff5c6a',
          borderColor: '#ff5c6a',
          order: 1,
        },
        {
          label: 'Exit',
          data: exits,
          type: 'scatter',
          pointStyle: 'circle',
          pointRadius: 4,
          backgroundColor: '#ffb454',
          borderColor: '#ffb454',
          order: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'nearest', intersect: false },
      plugins: {
        legend: { labels: { color: '#8a97a8', boxWidth: 12, font: { size: 11 } } },
        tooltip: {
          callbacks: {
            label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(5)}`
          }
        }
      },
      scales: {
        x: { type: 'time', time: { unit: 'day' }, ticks: { color: '#8a97a8' }, grid: { color: '#1b2531' } },
        y: { ticks: { color: '#8a97a8' }, grid: { color: '#1b2531' } },
      },
    },
  });
}

function renderEquityChart(equityCurve, startingBalance) {
  const points = equityCurve.map(p => ({ x: new Date(p.t).getTime(), y: p.equity }));
  const last = points.length ? points[points.length - 1].y : startingBalance;
  const isUp = last >= startingBalance;

  const ctx = document.getElementById('equityChart').getContext('2d');
  if (equityChart) equityChart.destroy();
  equityChart = new Chart(ctx, {
    type: 'line',
    data: {
      datasets: [
        {
          label: 'Equity',
          data: points,
          borderColor: isUp ? '#26d97a' : '#ff5c6a',
          backgroundColor: isUp ? 'rgba(38,217,122,0.08)' : 'rgba(255,92,106,0.08)',
          borderWidth: 1.8,
          pointRadius: 0,
          fill: true,
          tension: 0.2,
        },
        {
          label: 'Starting Balance',
          data: points.map(p => ({ x: p.x, y: startingBalance })),
          borderColor: '#3a4658',
          borderWidth: 1,
          borderDash: [4, 4],
          pointRadius: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: '#8a97a8', boxWidth: 12, font: { size: 11 } } },
        tooltip: {
          callbacks: {
            label: (ctx) => `${ctx.dataset.label}: $${ctx.parsed.y.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`
          }
        }
      },
      scales: {
        x: { type: 'time', time: { unit: 'day' }, ticks: { color: '#8a97a8' }, grid: { color: '#1b2531' } },
        y: { ticks: { color: '#8a97a8' }, grid: { color: '#1b2531' } },
      },
    },
  });
}

function renderTradesTable(trades) {
  const tbody = document.getElementById('trades-body');
  tbody.innerHTML = '';

  if (!trades.length) {
    tbody.innerHTML = '<tr class="empty-row"><td colspan="10">No trades yet — waiting for the next signal.</td></tr>';
    return;
  }

  for (const t of trades.slice().reverse()) {
    const tr = document.createElement('tr');
    const pnlClass = t.pnl >= 0 ? 'pnl-pos' : 'pnl-neg';
    const dirClass = t.direction === 'long' ? 'dir-long' : 'dir-short';
    tr.innerHTML = `
      <td>${t.id}</td>
      <td class="${dirClass}">${t.direction.toUpperCase()}</td>
      <td>${fmtTime(t.entry_time)}</td>
      <td>${t.entry_price.toFixed(5)}</td>
      <td>${fmtTime(t.exit_time)}</td>
      <td>${t.exit_price.toFixed(5)}</td>
      <td>${t.size_lots}</td>
      <td>${t.signal_strength.toFixed(2)}x</td>
      <td class="${pnlClass}">${fmtMoney(t.pnl)} (${fmtPct(t.pnl_pct)})</td>
      <td>${t.reason}</td>
    `;
    tbody.appendChild(tr);
  }
}

function setText(id, text, cls) {
  const el = document.getElementById(id);
  el.textContent = text;
  if (cls) {
    el.classList.remove('pos', 'neg');
    el.classList.add(cls);
  }
}

async function loadAndRender() {
  try {
    const [state, trades, priceHistory, equityCurve] = await Promise.all([
      fetchJSON('data/state.json'),
      fetchJSON('data/trades.json'),
      fetchJSON('data/price_history.json'),
      fetchJSON('data/equity_curve.json'),
    ]);

    const startBal = state.meta.starting_balance;
    const equity = state.account.equity;
    const pnl = equity - startBal;
    const pnlPct = (pnl / startBal) * 100;

    document.getElementById('meta-leverage').textContent = `1:${state.meta.leverage.toFixed(0)}`;
    document.getElementById('meta-start').textContent = fmtTime(state.meta.start_time);
    document.getElementById('meta-updated').textContent = fmtTime(state.meta.last_updated);

    setText('stat-equity', fmtMoney(equity));
    setText('stat-equity-pct', fmtPct(pnlPct), pnlPct >= 0 ? 'pos' : 'neg');
    setText('stat-balance', fmtMoney(state.account.balance));
    setText('stat-unrealized', fmtMoney(state.account.unrealized_pnl), state.account.unrealized_pnl >= 0 ? 'pos' : 'neg');

    if (state.open_position) {
      const p = state.open_position;
      setText('stat-position', p.direction.toUpperCase(), p.direction === 'long' ? 'pos' : 'neg');
      setText('stat-position-detail', `${p.size_lots} lots @ ${p.entry_price.toFixed(5)} (${p.signal_strength.toFixed(2)}x conviction)`);
    } else {
      setText('stat-position', 'FLAT');
      setText('stat-position-detail', 'No open position');
    }

    setText('stat-trades', state.account.total_trades);
    setText('stat-winrate', `${state.account.win_rate}% win rate`);
    setText('stat-drawdown', fmtPct(state.account.max_drawdown_pct), 'neg');

    if (priceHistory.length) {
      document.getElementById('live-price').textContent = priceHistory[priceHistory.length - 1].c.toFixed(5);
    }
    document.getElementById('equity-change').textContent = `${fmtMoney(pnl)} (${fmtPct(pnlPct)})`;

    renderPriceChart(priceHistory, trades);
    renderEquityChart(equityCurve, startBal);
    renderTradesTable(trades);
  } catch (err) {
    console.error('Failed to load paper trading data:', err);
  }
}

loadAndRender();
setInterval(loadAndRender, REFRESH_MS);
