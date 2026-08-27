// 任务触发与状态轮询
async function startTask(url, options) {  // 通用任务启动函数：请求 API 后进入轮询
  const resultEl = document.getElementById('result');  // 获取结果展示区元素
  resultEl.innerHTML = '<p class="muted">⏳ 任务已提交，正在执行…</p>';  // 先显示“已提交”占位
  try {  // 捕获请求异常
    const resp = await fetch(url, options);  // 异步请求后端任务 API
    const data = await resp.json();  // 解析 JSON 响应
    if (data.task_id) {  // 拿到 task_id 说明启动成功
      await pollTask(data.task_id, resultEl);  // 开始轮询该任务状态
    } else {  // 启动失败
      resultEl.innerHTML = '<p class="error">启动失败：' + JSON.stringify(data) + '</p>';  // 显示错误信息
    }
  } catch (e) {  // 网络异常等
    resultEl.innerHTML = '<p class="error">请求失败：' + escapeHtml(e.message) + '</p>';  // 转义后显示错误
  }
}

async function pollTask(taskId, resultEl) {  // 轮询任务状态直到结束
  while (true) {  // 无限循环，任务结束后 break
    await new Promise(r => setTimeout(r, 1000));  // 每 1 秒轮询一次
    const resp = await fetch('/api/tasks/' + taskId);  // 查询任务状态
    const task = await resp.json();  // 解析 JSON
    if (task.status === 'running') {  // 任务仍在执行
      resultEl.innerHTML = '<p class="muted">⏳ 任务执行中…</p>';  // 显示执行中
      continue;  // 继续下一轮轮询
    }
    renderResult(task, resultEl);  // 任务结束，渲染最终结果
    break;  // 退出循环
  }
}

function renderResult(task, resultEl) {  // 渲染任务最终结果
  const cls = task.status === 'success' ? 'ok' : (task.status === 'partial' ? 'warn' : 'error');  // 按状态选颜色类
  let html = '<p class="status-banner ' + cls + '">状态：' + escapeHtml(task.status) +  // 状态横幅：状态文字
             ' —— ' + escapeHtml(task.summary || '') + '</p>';  // 拼接摘要
  if (task.result_detail) {  // 有完整输出
    html += '<pre>' + escapeHtml(task.result_detail) + '</pre>';  // 用 pre 保留换行展示
  }
  resultEl.innerHTML = html;  // 写入页面
}

function startBackup() {  // 备份按钮点击处理
  startTask('/api/tasks/backup', { method: 'POST' });  // 触发备份任务
}

function startPortSecurity() {  // 扫描按钮点击处理
  startTask('/api/tasks/port-security', { method: 'POST' });  // 触发端口安全扫描任务
}

function startVlans(event) {  // 建 VLAN 表单提交处理
  event.preventDefault();  // 阻止表单默认提交刷新页面
  const body = {  // 组装请求体
    device_id: document.getElementById('vlan-device').value,  // 目标设备 ID
    vlan_start: document.getElementById('vlan-start').value,  // 起始 VLAN
    vlan_end: document.getElementById('vlan-end').value,  // 结束 VLAN
  };
  startTask('/api/tasks/vlans', {  // 触发建 VLAN 任务
    method: 'POST',  // POST 请求
    headers: { 'Content-Type': 'application/json' },  // 声明 JSON 请求体
    body: JSON.stringify(body),  // 把对象转 JSON 字符串
  });
  return false;  // 返回 false 进一步阻止默认提交
}

function escapeHtml(s) {  // HTML 转义函数，防 XSS
  return String(s).replace(/[&<>"']/g, c =>  // 把特殊字符逐个替换
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));  // 用映射表替换
}
