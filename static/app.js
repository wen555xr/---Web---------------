// 任务触发与状态轮询
async function startTask(url, options) {
  const resultEl = document.getElementById('result');
  resultEl.innerHTML = '<p class="muted">⏳ 任务已提交，正在执行…</p>';
  try {
    const resp = await fetch(url, options);
    const data = await resp.json();
    if (data.task_id) {
      await pollTask(data.task_id, resultEl);
    } else {
      resultEl.innerHTML = '<p class="error">启动失败：' + JSON.stringify(data) + '</p>';
    }
  } catch (e) {
    resultEl.innerHTML = '<p class="error">请求失败：' + escapeHtml(e.message) + '</p>';
  }
}

async function pollTask(taskId, resultEl) {
  while (true) {
    await new Promise(r => setTimeout(r, 1000));
    const resp = await fetch('/api/tasks/' + taskId);
    const task = await resp.json();
    if (task.status === 'running') {
      resultEl.innerHTML = '<p class="muted">⏳ 任务执行中…</p>';
      continue;
    }
    renderResult(task, resultEl);
    break;
  }
}

function renderResult(task, resultEl) {
  const cls = task.status === 'success' ? 'ok' : (task.status === 'partial' ? 'warn' : 'error');
  let html = '<p class="status-banner ' + cls + '">状态：' + escapeHtml(task.status) +
             ' —— ' + escapeHtml(task.summary || '') + '</p>';
  if (task.result_detail) {
    html += '<pre>' + escapeHtml(task.result_detail) + '</pre>';
  }
  resultEl.innerHTML = html;
}

function startBackup() {
  startTask('/api/tasks/backup', { method: 'POST' });
}

function startPortSecurity() {
  startTask('/api/tasks/port-security', { method: 'POST' });
}

function startVlans(event) {
  event.preventDefault();
  const body = {
    device_id: document.getElementById('vlan-device').value,
    vlan_start: document.getElementById('vlan-start').value,
    vlan_end: document.getElementById('vlan-end').value,
  };
  startTask('/api/tasks/vlans', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return false;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
