const BASE = "/api/workforce"

function getAuthHeader() {
  const token =
    process.env.NEXT_PUBLIC_AZIZ_API_TOKEN ||
    process.env.AZIZ_API_TOKEN ||
    "dev-token"
  return { Authorization: `Bearer ${token}` }
}

async function fetchJson(url: string, init?: RequestInit) {
  const res = await fetch(url, {
    ...init,
    headers: {
      ...getAuthHeader(),
      ...(init?.headers || {}),
    },
    cache: "no-store",
  })
  return res.json()
}

export async function get_overview() {
  return fetchJson(`${BASE}/overview`)
}

export async function get_workers(status?: string) {
  const params = status ? `?status=${status}` : ""
  return fetchJson(`${BASE}/workers${params}`)
}

export async function get_worker(agent_id: string) {
  return fetchJson(`${BASE}/workers/${agent_id}`)
}

export async function get_teams() {
  return fetchJson(`${BASE}/teams`)
}

export async function get_tasks(status?: string) {
  const params = status ? `?status=${status}` : ""
  return fetchJson(`${BASE}/tasks${params}`)
}

export async function get_task(task_id: string) {
  return fetchJson(`${BASE}/tasks/${task_id}`)
}

export async function create_task(title: string, description?: string, priority?: string) {
  return fetchJson(`${BASE}/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title,
      description,
      priority,
      task_type: "research",
      input_data: {
        symbol: "THYAO.IS",
        timeframe: "1h",
      },
      requirements: ["RESEARCH"],
    }),
  })
}

export async function assign_task(task_id: string, agent_id: string) {
  return fetchJson(`${BASE}/tasks/${task_id}/assign`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ agent_id }),
  })
}

export async function start_task(task_id: string) {
  return fetchJson(`${BASE}/tasks/${task_id}/start`, { method: "POST" })
}

export async function complete_task(task_id: string, result?: Record<string, unknown>) {
  return fetchJson(`${BASE}/tasks/${task_id}/complete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ result }),
  })
}

export async function fail_task(task_id: string, error?: string) {
  return fetchJson(`${BASE}/tasks/${task_id}/fail`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ error: error ?? "Unknown error" }),
  })
}

export async function cancel_task(task_id: string) {
  return fetchJson(`${BASE}/tasks/${task_id}/cancel`, { method: "POST" })
}

export async function get_approvals(status = "PENDING") {
  return fetchJson(`${BASE}/approvals?status=${status}`)
}

export async function decide_approval(approval_id: string, decision: string, decided_by = "patron") {
  return fetchJson(`${BASE}/approvals/${approval_id}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision, decided_by }),
  })
}

export async function get_health() {
  return fetchJson(`${BASE}/health`)
}
