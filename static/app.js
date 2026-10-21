'use strict';
const $ = id => document.getElementById(id);
const number = value => new Intl.NumberFormat('en-US').format(value);
let data = null, pending = false;
function cell(row, value, css) { const el = document.createElement('td'); el.textContent = value; if (css) el.className = css; row.append(el); }
function table(id, rows, render, emptyMessage) {
  $(id).replaceChildren();
  if (!rows.length) { const tr = document.createElement('tr'); const td = document.createElement('td'); td.colSpan = $(id).closest('table').querySelectorAll('thead th').length; td.className = 'empty'; td.textContent = emptyMessage || 'No tracked commands for this period and project.'; tr.append(td); $(id).append(tr); }
  rows.forEach(item => { const row = document.createElement('tr'); render(row, item); $(id).append(row); });
}
function cost() {
  const price = Number($('price').value);
  $('cost').textContent = new Intl.NumberFormat('en-US', {style:'currency',currency:'USD',maximumFractionDigits:4}).format((data?.totals.saved || 0) * (Number.isFinite(price) && price >= 0 && price <= 10000 ? price : 0) / 1000000);
}
function render(result) {
  data = result;
  const t = data.totals;
  $('saved').textContent = number(t.saved); $('percent').textContent = `${t.percent}%`;
  $('output').textContent = number(t.output); $('input').textContent = `${number(t.input)} raw output tokens`;
  $('count').textContent = number(t.commands); $('ratio').textContent = `${t.percent}%`;
  $('meter').style.width = `${Math.max(0, Math.min(100, t.percent))}%`;
  $('efficiency').textContent = `${number(t.input)} raw tokens → ${number(t.output)} tokens`;
  $('gross-saved').textContent = number(t.gross_saved);
  $('expansion').textContent = `−${number(t.expansion)}`;
  $('net-saved').textContent = number(t.saved);
  const last = t.last_record ? new Date(t.last_record) : null;
  const stale = last && Date.now() - last.getTime() > 86400000;
  $('coverage').classList.toggle('stale', Boolean(stale));
  $('coverage').textContent = last ? `Last tracked RTK command: ${last.toLocaleString('en-US', {timeZone:'UTC'})} UTC.${stale ? ' No new RTK command has been recorded in over 24 hours.' : ''} Savings cover tracked command outputs only, across your tools; session token usage is separate.` : 'No RTK commands recorded for these filters. Model sessions may still contain usage.';
  const selected = $('project').value;
  $('project').replaceChildren(new Option('All projects', ''));
  const projectNames = data.projects.map(p => p.split('/').filter(Boolean).pop());
  data.projects.forEach((p, i) => {
    const name = projectNames[i];
    const option = new Option(projectNames.filter(n => n === name).length > 1 ? `${name} · ${p}` : name, p);
    option.title = p;
    $('project').add(option);
  });
  $('project').value = selected;
  table('groups', data.groups, (row, r) => { cell(row, r.name); cell(row, number(r.commands)); cell(row, number(r.input)); cell(row, number(r.saved), r.saved < 0 ? 'negative' : 'saving'); cell(row, `${r.input ? (r.saved/r.input*100).toFixed(1) : 0}%`); });
  table('recent', data.recent, (row, r) => { cell(row, r.timestamp.replace('T', ' ').slice(0,19)); cell(row, r.name); cell(row, number(r.input)); cell(row, number(r.output)); cell(row, number(r.saved), r.saved < 0 ? 'negative' : 'saving'); });
  const usage = data.model_usage;
  $('model-status').textContent = !usage.available ? 'No local session directories found.' : usage.unreadable_files ? `${number(usage.unreadable_files)} session files could not be read; results may be incomplete.` : `${usage.sources.map(s => `${s.name}: ${s.available ? 'available' : 'session directory not found'}`).join(' · ')} · Local session records`;
  table('model-rows', usage.rows, (row, r) => { cell(row, r.source); cell(row, r.name); cell(row, number(r.input)); cell(row, number(r.cached)); cell(row, number(r.cache_write)); cell(row, number(r.output)); cell(row, number(r.input + r.output), 'saving'); }, 'No model usage for this period and project.');
  const mt = usage.totals;
  $('model-input').textContent = number(mt.input);
  $('model-cache').textContent = number(mt.cached);
  $('model-output').textContent = number(mt.output);
  $('chart').replaceChildren();
  const peak = Math.max(1, ...data.daily.map(d => Math.max(d.input, d.output)));
  $('chart-peak').textContent = number(data.daily.length ? peak : 0);
  $('chart-days').textContent = `${number(data.daily.length)} recorded days`;
  if (!data.daily.length) { const e = document.createElement('p'); e.className = 'empty'; e.textContent = 'No tracked commands for this period.'; $('chart').append(e); }
  data.daily.forEach((d, i) => {
    const day = document.createElement('div'); day.className = 'bar-day';
    day.title = `${d.day} · Raw: ${number(d.input)} · RTK: ${number(d.output)} · Net saved: ${number(d.saved)}`;
    const track = document.createElement('div'); track.className = 'bar-track';
    [d.input, d.output].forEach((n, j) => { const b = document.createElement('div'); b.className = j ? 'bar out' : 'bar'; b.style.height = `${Math.max(0,n/peak*100)}%`; track.append(b); });
    const label = document.createElement('span'); label.className = 'day-label'; label.textContent = i % Math.max(1, Math.ceil(data.daily.length/9)) === 0 ? d.day.slice(5).replace('-', '/') : '';
    day.append(track, label); $('chart').append(day);
  });
  $('chart').setAttribute('aria-label', `${data.daily.length} recorded days: ${number(t.input)} raw output tokens, ${number(t.output)} after RTK. Daily values are available in bar descriptions.`);
  cost();
}
async function load() {
  if (pending) return;
  pending = true; $('refresh').disabled = true; $('days').disabled = true; $('project').disabled = true; $('content').setAttribute('aria-busy', 'true');
  try {
    const query = new URLSearchParams({days:$('days').value, project:$('project').value});
    const response = await fetch(`/api/data?${query}`, {signal:AbortSignal.timeout(10000)});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Unable to read usage data.');
    render(result); $('content').hidden = false; $('error').hidden = true;
    $('status').textContent = `Updated · ${new Date().toLocaleTimeString('en-US')}`;
  } catch (error) {
    $('error').textContent = error.message; $('error').hidden = false; $('content').hidden = true; $('status').textContent = 'Data unavailable';
  } finally {
    pending = false; $('refresh').disabled = false; $('days').disabled = false; $('project').disabled = false; $('content').setAttribute('aria-busy', 'false');
  }
}
$('refresh').addEventListener('click', load); $('days').addEventListener('change', load); $('project').addEventListener('change', load); $('price').addEventListener('input', cost);
setInterval(() => { if (!document.hidden) load(); }, 30000); load();
