#!/usr/bin/env node
import http from 'node:http'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const arg = (name, fallback) => process.argv.find(item => item.startsWith(`--${name}=`))?.split('=', 2)[1] || fallback
const port = Number(arg('port', '8787'))
const host = arg('host', '127.0.0.1')
const backendUrl = arg('backend', process.env.JD_COLLECTOR_BACKEND || 'http://127.0.0.1:8001').replace(/\/$/, '')
const root = path.dirname(fileURLToPath(import.meta.url))
const adaptersRoot = path.join(root, 'adapters')
const adapters = [
  { id: 'auto', label: '自动识别站点' },
  { id: 'boss-zhipin', label: 'BOSS 直聘', file: 'boss-zhipin.js' },
  { id: 'mokahr', label: 'Mokahr', file: 'mokahr.js' },
  { id: 'lagou', label: '拉勾', file: 'lagou.js' },
  { id: 'liepin', label: '猎聘', file: 'liepin.js' },
  { id: 'dachang-spa', label: '大厂招聘 SPA', file: 'dachang-spa.js' },
  { id: 'universal', label: '通用网页', file: 'universal.js' },
]

const cors = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
}

function jsonResponse(res, status, payload) {
  const body = JSON.stringify(payload)
  res.writeHead(status, { ...cors, 'Content-Type': 'application/json; charset=utf-8', 'Content-Length': Buffer.byteLength(body) })
  res.end(body)
}

function escapeHtml(value) {
  return value.replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char])
}

function autoBookmarklet(projectId) {
  const endpoint = `http://${host}:${port}/jd?project_id=${encodeURIComponent(projectId)}`
  return `javascript:(async()=>{const h=location.hostname;const site=h.includes('zhipin.com')?'boss-zhipin':h.includes('mokahr.com')?'mokahr':h.includes('lagou.com')?'lagou':h.includes('liepin.com')?'liepin':/(jobs|career|talent).*(bytedance|tencent|alibaba|jd|meituan|xiaomi|huawei)/i.test(h)?'dachang-spa':'universal';const exclude='.dialog,.modal,[class*="download"],[class*="recommend"],[class*="related"],[class*="similar"],[class*="side"],nav,footer';const sets={"boss-zhipin":['.job-detail-section','.job-sec-text','.job-detail-content','.job-detail'],mokahr:['.job-description','[class*="jobDescription"]','[class*="description"]'],lagou:['.job-detail','.position-content-l','.job_bt'],liepin:['.job-intro-container','.job-description','.content-word'],"dachang-spa":['[class*="position-description"]','[class*="job-description"]','[class*="jobDetail"]'],universal:['[class*="job-description"]','[class*="job-detail"]','[class*="position-description"]','main']};const clean=e=>{if(!e)return'';const c=e.cloneNode(true);c.querySelectorAll(exclude).forEach(x=>x.remove());return(c.innerText||c.textContent||'').trim()};const candidates=(sets[site]||sets.universal).flatMap(s=>[...document.querySelectorAll(s)]).map(clean).filter(Boolean).sort((a,b)=>b.length-a.length);const description=candidates[0]||'';const title=(document.querySelector('h1,[class*="job-title"],[class*="job-name"]')?.innerText||document.title||'网页岗位').trim();try{const r=await fetch(${JSON.stringify(endpoint)},{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({page_title:document.title,url:location.href,platform:site,extracted:{job_title:title,description,raw_text:description}})});const x=await r.json();alert(r.ok&&x.ok?'JD 已导入当前任务并完成模型解析':'提取失败：'+(x.detail||x.error||r.status))}catch(e){alert('无法连接本地 JD 提取服务：'+e.message)}})()`
}

function adapterBookmarklet(adapter, projectId) {
  if (adapter.id === 'auto') return autoBookmarklet(projectId)
  const endpoint = `http://${host}:${port}/jd?project_id=${encodeURIComponent(projectId)}`
  const source = fs.readFileSync(path.join(adaptersRoot, adapter.file), 'utf8')
  const start = source.indexOf('(async function')
  const executable = start >= 0 ? source.slice(start) : source
  return `javascript:${executable.replaceAll('http://localhost:8787/jd', endpoint)}`
}

function installPage(projectId) {
  const buttons = adapters.map(adapter => `<div class="adapter"><a class="button" href="${escapeHtml(adapterBookmarklet(adapter, projectId))}">${escapeHtml(adapter.label)}</a><span>${adapter.id === 'auto' ? '根据当前网址自动选择适配器（推荐）' : '站点专用提取器'}</span></div>`).join('')
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>安装 JD 提取工具</title><style>body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif;max-width:820px;margin:48px auto;padding:0 20px;color:#193532;background:#f7f3eb}.card{background:#fff;border:1px solid #d7e1dc;border-radius:16px;padding:28px;box-shadow:0 10px 30px #24443b12}.adapter{display:flex;align-items:center;gap:14px;padding:10px 0;border-bottom:1px solid #edf1ef}.adapter span{color:#60716c;font-size:14px}.button{display:inline-block;min-width:150px;text-align:center;background:#267365;color:#fff;text-decoration:none;padding:12px 18px;border-radius:10px;font-weight:700;cursor:grab}.adapter:first-child .button{background:#174f46}.meta{margin-top:20px;padding:12px;background:#eef5f1;border-radius:8px;word-break:break-all}li{margin:8px 0}</style></head><body><main class="card"><h1>当前任务 JD 提取工具</h1><p>此书签已绑定任务：<strong>${escapeHtml(projectId)}</strong></p><ol><li>显示浏览器书签栏。</li><li>优先把“自动识别站点”拖到浏览器书签栏，也可安装站点专用书签。</li><li>打开 JD 详情页并点击书签。</li><li>系统确认正文有效、保存和解析完成后才会显示成功提示。</li></ol>${buttons}<p class="meta">Collector：${escapeHtml(`http://${host}:${port}`)}<br>Backend：${escapeHtml(backendUrl)}</p></main></body></html>`
}

function validateCapture(payload) {
  const extracted = payload?.extracted && typeof payload.extracted === 'object' ? payload.extracted : payload
  const text = String(extracted?.description || extracted?.raw_text || '').replace(/\s+/g, ' ').trim()
  const noise = /下载\s*App|不错过.*消息|扫码.*下载|打开.*App|登录后查看|安全验证/i
  const jdSignal = /岗位职责|职位描述|任职要求|工作内容|负责|要求|经验|能力|熟悉|掌握/i
  if (text.length < 50 || noise.test(text) || !jdSignal.test(text)) {
    return { valid: false, detail: '没有提取到有效 JD 正文。请关闭下载 App/登录弹窗后，使用对应站点的专用提取器重试。' }
  }
  return { valid: true }
}

async function readJson(req) {
  let body = ''
  for await (const chunk of req) {
    body += chunk
    if (body.length > 5_000_000) throw new Error('payload too large')
  }
  return JSON.parse(body)
}

const server = http.createServer(async (req, res) => {
  if (req.method === 'OPTIONS') {
    res.writeHead(204, cors)
    return res.end()
  }
  const requestUrl = new URL(req.url || '/', `http://${req.headers.host || `${host}:${port}`}`)
  if (req.method === 'GET' && requestUrl.pathname === '/health') {
    res.writeHead(200, { ...cors, 'Content-Type': 'text/plain; charset=utf-8' })
    return res.end('ok')
  }
  if (req.method === 'GET' && requestUrl.pathname === '/install') {
    const projectId = requestUrl.searchParams.get('project_id')?.trim()
    if (!projectId) return jsonResponse(res, 422, { detail: 'project_id 不能为空' })
    const body = installPage(projectId)
    res.writeHead(200, { ...cors, 'Content-Type': 'text/html; charset=utf-8', 'Content-Length': Buffer.byteLength(body) })
    return res.end(body)
  }
  if (req.method === 'POST' && requestUrl.pathname === '/jd') {
    const projectId = requestUrl.searchParams.get('project_id')?.trim()
    if (!projectId) return jsonResponse(res, 422, { ok: false, detail: 'project_id 不能为空' })
    try {
      const payload = await readJson(req)
      const validation = validateCapture(payload)
      if (!validation.valid) return jsonResponse(res, 422, { ok: false, project_id: projectId, detail: validation.detail })
      const response = await fetch(`${backendUrl}/api/projects/${encodeURIComponent(projectId)}/jds/browser`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const result = await response.json().catch(() => ({}))
      if (!response.ok) {
        return jsonResponse(res, 502, { ok: false, project_id: projectId, detail: result.detail || `后端返回 ${response.status}` })
      }
      if (result.status !== 'COMPLETED') {
        return jsonResponse(res, 422, {
          ok: false,
          project_id: projectId,
          jd_id: result.id,
          detail: 'JD 已保存，但没有解析出可回溯的能力项。请检查网页正文后重新提取。',
        })
      }
      return jsonResponse(res, 200, {
        ok: true,
        project_id: projectId,
        file: `当前任务 ${projectId}`,
        jd_id: result.id,
        jd_status: result.status,
      })
    } catch (error) {
      return jsonResponse(res, 502, { ok: false, project_id: projectId, detail: String(error.message || error) })
    }
  }
  return jsonResponse(res, 404, { detail: 'Not Found' })
})

server.listen(port, host, () => {
  console.log(`JD Collector listening on http://${host}:${port}`)
  console.log(`Forwarding captures to ${backendUrl}`)
})
