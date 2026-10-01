<template>
  <section class="page" data-module="safetyfee">
    <header class="page-head">
      <div>
        <h2>安全费用台账</h2>
        <p class="page-desc">
          按项目与年度核算应提，提取比例只走已发布口径；提取与使用分开登记，
          超额当场驳回，同票只认一次，跨单位提交当场驳回。
        </p>
      </div>
      <div class="page-actions identity-box">
        <label class="filter-item">
          <span>当前登记人（安全员）</span>
          <input v-model="identity.operator" placeholder="姓名" />
        </label>
        <label class="filter-item">
          <span>所属单位</span>
          <input v-model="identity.unit" placeholder="单位名称" />
        </label>
      </div>
    </header>

    <div class="sf-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="sf-tab"
        :class="{ active: activeTab === tab.key }"
        type="button"
        @click="activeTab = tab.key"
      >
        {{ tab.label }}
      </button>
    </div>

    <p v-if="message" class="inline-msg" :class="messageOk ? 'ok-text' : 'error-text'">{{ message }}</p>

    <!-- ============ 项目台账 ============ -->
    <div v-if="activeTab === 'ledger'">
      <div class="stat-row">
        <article class="stat-card">
          <span class="stat-label">累计应提（现行口径）</span>
          <strong class="stat-value">{{ money(ledgerTotal.已提金额) }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">累计已使用</span>
          <strong class="stat-value">{{ money(ledgerTotal.已用金额) }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">累计余额</span>
          <strong class="stat-value">{{ money(ledgerTotal.余额) }}</strong>
        </article>
      </div>

      <form class="filter-bar" @submit.prevent="loadLedger">
        <label class="filter-item">
          <span>项目</span>
          <select v-model="ledgerFilter.projectId">
            <option value="">全部项目</option>
            <option v-for="p in projects" :key="String(p.id)" :value="String(p.id)">{{ p.项目名称 }}</option>
          </select>
        </label>
        <label class="filter-item">
          <span>年度</span>
          <input v-model="ledgerFilter.year" placeholder="如 2026" style="width: 100px" />
        </label>
        <button class="btn" type="submit">查询</button>
      </form>

      <table class="data-table">
        <thead>
          <tr>
            <th>项目</th><th>所属单位</th><th>安全员</th><th>年度</th>
            <th>适用口径</th><th>提取比例</th><th>已提金额</th><th>已用金额</th><th>余额</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in ledgerRows" :key="`${row.项目ID}-${row.年度}`">
            <td>{{ row.项目名称 }}</td>
            <td>{{ row.所属单位 }}</td>
            <td>{{ row.安全员 }}</td>
            <td>{{ row.年度 }}</td>
            <td>{{ row.适用版本 ?? '—' }}</td>
            <td>{{ row.提取比例 == null ? '—' : `${row.提取比例}%` }}</td>
            <td>{{ money(row.已提金额) }}</td>
            <td>{{ money(row.已用金额) }}</td>
            <td :class="Number(row.余额) < 0 ? 'error-text' : ''">{{ money(row.余额) }}</td>
          </tr>
          <tr v-if="!ledgerRows.length">
            <td colspan="9" class="empty-state">暂无台账数据，请先维护年度计提基数</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- ============ 计提基数与提取登记 ============ -->
    <div v-if="activeTab === 'accrual'">
      <div class="sf-cols">
        <form class="sf-panel" @submit.prevent="submitBase">
          <h3>维护年度计提基数</h3>
          <p class="page-desc">保存基数时若该年度已有适用口径，会自动重算应提。</p>
          <label class="filter-item"><span>项目</span>
            <select v-model="baseForm.projectId" required>
              <option value="" disabled>请选择项目</option>
              <option v-for="p in projects" :key="String(p.id)" :value="String(p.id)">{{ p.项目名称 }}</option>
            </select>
          </label>
          <label class="filter-item"><span>年度</span><input v-model="baseForm.year" required placeholder="如 2026" /></label>
          <label class="filter-item"><span>年度计提基数（元）</span><input v-model="baseForm.amount" required placeholder="如 10000000" /></label>
          <button class="btn primary" type="submit">保存基数并重算应提</button>
        </form>

        <form class="sf-panel" @submit.prevent="submitAccrual">
          <h3>提取登记</h3>
          <p class="page-desc">比例自动取该年度最新发布口径；同一项目同一年度同一口径重复登记只认第一次。</p>
          <label class="filter-item"><span>项目</span>
            <select v-model="accrualForm.projectId" required>
              <option value="" disabled>请选择项目</option>
              <option v-for="p in projects" :key="String(p.id)" :value="String(p.id)">{{ p.项目名称 }}</option>
            </select>
          </label>
          <label class="filter-item"><span>年度</span><input v-model="accrualForm.year" required placeholder="如 2026" /></label>
          <button class="btn primary" type="submit">按发布口径登记提取</button>
        </form>
      </div>

      <h3>提取登记明细（含历史口径版本）</h3>
      <table class="data-table">
        <thead>
          <tr>
            <th>项目</th><th>年度</th><th>口径版本</th><th>提取比例</th>
            <th>计提基数</th><th>应提金额</th><th>来源</th><th>登记日期</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in accrualRows" :key="String(row.id)">
            <td>{{ projectName(row.项目ID) }}</td>
            <td>{{ row.年度 }}</td>
            <td>{{ row.版本名称 }}</td>
            <td>{{ row.提取比例 }}%</td>
            <td>{{ money(row.计提基数) }}</td>
            <td>{{ money(row.应提金额) }}</td>
            <td>{{ row.来源 }}</td>
            <td>{{ row.登记日期 ?? '—' }}</td>
          </tr>
          <tr v-if="!accrualRows.length"><td colspan="8" class="empty-state">暂无提取登记</td></tr>
        </tbody>
      </table>
    </div>

    <!-- ============ 使用登记 ============ -->
    <div v-if="activeTab === 'usage'">
      <form class="sf-panel wide" @submit.prevent="submitUsage">
        <h3>安全费用使用登记</h3>
        <div class="sf-cols">
          <label class="filter-item"><span>项目</span>
            <select v-model="usageForm.projectId" required>
              <option value="" disabled>请选择项目</option>
              <option v-for="p in projects" :key="String(p.id)" :value="String(p.id)">{{ p.项目名称 }}</option>
            </select>
          </label>
          <label class="filter-item"><span>使用年度</span><input v-model="usageForm.year" required placeholder="如 2026" /></label>
          <label class="filter-item"><span>使用金额（元）</span><input v-model="usageForm.amount" required placeholder="如 20000" /></label>
          <label class="filter-item"><span>发票号码</span><input v-model="usageForm.invoiceNo" required placeholder="同票只生效一次" /></label>
          <label class="filter-item"><span>用途</span><input v-model="usageForm.purpose" placeholder="如 隐患排查治理" /></label>
          <label class="filter-item"><span>登记日期</span><input v-model="usageForm.date" type="date" /></label>
        </div>
        <p class="page-desc">
          登记人取页首身份；只有所选项目的本单位安全员能提交，跨单位当场驳回。
          <template v-if="selectedProject">
            当前所选项目要求：安全员 <strong>{{ selectedProject.安全员 }}</strong>，
            所属单位 <strong>{{ selectedProject.所属单位 }}</strong>。
          </template>
        </p>
        <button class="btn primary" type="submit">提交使用登记</button>
      </form>

      <div class="stat-row">
        <article class="stat-card">
          <span class="stat-label">使用合计（随每笔登记重算）</span>
          <strong class="stat-value">{{ money(usageSummary.合计金额) }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">报销笔数</span>
          <strong class="stat-value">{{ usageSummary.笔数 }}</strong>
        </article>
      </div>

      <form class="filter-bar" @submit.prevent="loadUsages">
        <label class="filter-item">
          <span>项目</span>
          <select v-model="usageFilter.projectId">
            <option value="">全部项目</option>
            <option v-for="p in projects" :key="String(p.id)" :value="String(p.id)">{{ p.项目名称 }}</option>
          </select>
        </label>
        <label class="filter-item"><span>年度</span><input v-model="usageFilter.year" placeholder="如 2026" /></label>
        <label class="filter-item"><span>发票号码</span><input v-model="usageFilter.invoiceNo" placeholder="按发票检索" /></label>
        <button class="btn" type="submit">查询</button>
      </form>

      <table class="data-table">
        <thead>
          <tr>
            <th>项目</th><th>年度</th><th>使用金额</th><th>用途</th>
            <th>发票号码</th><th>登记人</th><th>登记人单位</th><th>登记日期</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in usageRows" :key="String(row.id)">
            <td>{{ row.项目名称 }}</td>
            <td>{{ row.年度 }}</td>
            <td>{{ money(row.使用金额) }}</td>
            <td>{{ row.用途 ?? '—' }}</td>
            <td>{{ row.发票号码 }}</td>
            <td>{{ row.登记人 }}</td>
            <td>{{ row.登记人单位 }}</td>
            <td>{{ row.登记日期 ?? '—' }}</td>
          </tr>
          <tr v-if="!usageRows.length"><td colspan="8" class="empty-state">暂无使用明细</td></tr>
        </tbody>
      </table>
    </div>

    <!-- ============ 提取口径版本 ============ -->
    <div v-if="activeTab === 'policy'">
      <form class="sf-panel wide" @submit.prevent="submitPolicy">
        <h3>发布提取口径版本</h3>
        <p class="page-desc">
          提取比例只能从发布口径进入系统。新版本发布后，自生效年度起的存量应提会当场重填一版；
          历史年度台账仍按当时版本保留。
        </p>
        <div class="sf-cols">
          <label class="filter-item"><span>版本名称（文号）</span><input v-model="policyForm.name" required placeholder="如 财安〔2027〕2号" /></label>
          <label class="filter-item"><span>提取比例（%）</span><input v-model="policyForm.rate" required placeholder="如 2.5" /></label>
          <label class="filter-item"><span>生效年度</span><input v-model="policyForm.year" required placeholder="如 2027" /></label>
          <label class="filter-item"><span>发布日期</span><input v-model="policyForm.date" type="date" /></label>
        </div>
        <label class="filter-item"><span>说明</span><input v-model="policyForm.note" placeholder="口径调整说明" style="width: 100%" /></label>
        <button class="btn primary" type="submit">发布并重填存量</button>
      </form>

      <table class="data-table">
        <thead>
          <tr><th>版本名称</th><th>提取比例</th><th>生效年度</th><th>发布日期</th><th>说明</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in policies" :key="String(row.id)">
            <td>{{ row.版本名称 }}</td>
            <td>{{ row.提取比例 }}%</td>
            <td>{{ row.生效年度 }}</td>
            <td>{{ row.发布日期 ?? '—' }}</td>
            <td>{{ row.说明 ?? '—' }}</td>
          </tr>
          <tr v-if="!policies.length"><td colspan="5" class="empty-state">尚未发布任何口径</td></tr>
        </tbody>
      </table>
    </div>

    <footer class="page-foot">
      <span>台账、提取、使用共用同一份后端聚合数据，重启后端后示例数据复位</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

interface ApiList<T> { total: number; items: T[] }

const tabs = [
  { key: 'ledger', label: '项目台账' },
  { key: 'accrual', label: '计提基数与提取' },
  { key: 'usage', label: '使用登记与明细' },
  { key: 'policy', label: '提取口径版本' },
] as const

const activeTab = ref<(typeof tabs)[number]['key']>('ledger')
const message = ref('')
const messageOk = ref(false)

const projects = ref<Row[]>([])
const ledgerRows = ref<Row[]>([])
const ledgerTotal = ref<Row>({ 已提金额: 0, 已用金额: 0, 余额: 0 })
const accrualRows = ref<Row[]>([])
const usageRows = ref<Row[]>([])
const usageSummary = ref<Row>({ 笔数: 0, 合计金额: 0 })
const policies = ref<Row[]>([])

const ledgerFilter = reactive({ projectId: '', year: '' })
const usageFilter = reactive({ projectId: '', year: '', invoiceNo: '' })
const identity = reactive({ operator: '周建平', unit: '临港热力有限公司' })

const baseForm = reactive({ projectId: '', year: '', amount: '' })
const accrualForm = reactive({ projectId: '', year: '' })
const usageForm = reactive({
  projectId: '', year: '', amount: '', invoiceNo: '', purpose: '', date: '',
})
const policyForm = reactive({ name: '', rate: '', year: '', date: '', note: '' })

const selectedProject = computed(() =>
  projects.value.find((p) => String(p.id) === usageForm.projectId) ?? null,
)

function money(value: unknown): string {
  const n = Number(value ?? 0)
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function projectName(id: number | string | null): string {
  return projects.value.find((p) => String(p.id) === String(id))?.项目名称 as string ?? `项目${id}`
}

function flash(ok: boolean, text: string) {
  messageOk.value = ok
  message.value = text
}

async function getJson<T>(path: string): Promise<T> {
  const response = await request(path)
  if (!response.ok) throw new Error(`接口返回 ${response.status}`)
  return (await response.json()) as T
}

async function postAction(path: string, values: Record<string, unknown>): Promise<{ ok: boolean; message: string }> {
  const response = await request(path, {
    method: 'POST',
    body: JSON.stringify({ values }),
  })
  if (!response.ok) throw new Error(`接口返回 ${response.status}`)
  return (await response.json()) as { ok: boolean; message: string }
}

async function loadProjects() {
  const data = await getJson<ApiList<Row>>('/api/safetyfee/projects')
  projects.value = data.items
}

async function loadPolicies() {
  const data = await getJson<ApiList<Row>>('/api/safetyfee/policies')
  policies.value = data.items
}

async function loadLedger() {
  const params = new URLSearchParams()
  if (ledgerFilter.projectId) params.set('项目ID', ledgerFilter.projectId)
  if (ledgerFilter.year) params.set('年度', ledgerFilter.year)
  const data = await getJson<{ items: Row[]; 合计: Row }>(`/api/safetyfee/ledger?${params.toString()}`)
  ledgerRows.value = data.items
  ledgerTotal.value = data.合计
}

async function loadAccruals() {
  const data = await getJson<ApiList<Row>>('/api/safetyfee/accruals')
  accrualRows.value = [...data.items].sort(
    (a, b) => Number(a.年度) - Number(b.年度) || Number(a.项目ID) - Number(b.项目ID),
  )
}

async function loadUsages() {
  const params = new URLSearchParams()
  if (usageFilter.projectId) params.set('项目ID', usageFilter.projectId)
  if (usageFilter.year) params.set('年度', usageFilter.year)
  if (usageFilter.invoiceNo) params.set('发票号码', usageFilter.invoiceNo)
  const query = params.toString()
  const [list, summary] = await Promise.all([
    getJson<ApiList<Row>>(`/api/safetyfee/usages?${query}`),
    getJson<Row>(`/api/safetyfee/usages/summary?${query}`),
  ])
  usageRows.value = list.items
  usageSummary.value = summary
}

async function refreshAll() {
  await Promise.all([loadLedger(), loadAccruals(), loadUsages(), loadPolicies()])
}

async function submitBase() {
  try {
    const result = await postAction('/api/safetyfee/bases', {
      项目ID: Number(baseForm.projectId),
      年度: Number(baseForm.year),
      年度基数: Number(baseForm.amount),
    })
    flash(result.ok, result.message)
    if (result.ok) {
      baseForm.amount = ''
      await refreshAll()
    }
  } catch (error) {
    flash(false, error instanceof Error ? error.message : '基数保存失败')
  }
}

async function submitAccrual() {
  try {
    const result = await postAction('/api/safetyfee/accruals/register', {
      项目ID: Number(accrualForm.projectId),
      年度: Number(accrualForm.year),
    })
    // 重复登记只认第一次属于业务提示（ok=false），但不是系统错误，按普通消息展示
    flash(result.ok, result.message)
    await refreshAll()
  } catch (error) {
    flash(false, error instanceof Error ? error.message : '提取登记失败')
  }
}

async function submitUsage() {
  try {
    const result = await postAction('/api/safetyfee/usages/register', {
      项目ID: Number(usageForm.projectId),
      年度: Number(usageForm.year),
      使用金额: Number(usageForm.amount),
      发票号码: usageForm.invoiceNo,
      用途: usageForm.purpose,
      登记日期: usageForm.date,
      登记人: identity.operator,
      登记人单位: identity.unit,
    })
    flash(result.ok, result.message)
    if (result.ok) {
      usageForm.amount = ''
      usageForm.invoiceNo = ''
      usageForm.purpose = ''
      await refreshAll()
    }
  } catch (error) {
    flash(false, error instanceof Error ? error.message : '使用登记失败')
  }
}

async function submitPolicy() {
  try {
    const result = await postAction('/api/safetyfee/policies', {
      版本名称: policyForm.name,
      提取比例: Number(policyForm.rate),
      生效年度: Number(policyForm.year),
      发布日期: policyForm.date,
      说明: policyForm.note,
    })
    flash(result.ok, result.message)
    if (result.ok) {
      policyForm.name = policyForm.rate = policyForm.year = policyForm.date = policyForm.note = ''
      await refreshAll()
    }
  } catch (error) {
    flash(false, error instanceof Error ? error.message : '口径发布失败')
  }
}

onMounted(async () => {
  try {
    await loadProjects()
    await refreshAll()
  } catch (error) {
    flash(false, error instanceof Error ? error.message : '台账数据加载失败')
  }
})
</script>

<style scoped>
.identity-box { gap: 10px; align-items: flex-end; }
.sf-tabs { display: flex; gap: 6px; margin: 8px 0 12px; }
.sf-tab { border: 1px solid var(--border); background: #fff; border-radius: 6px 6px 0 0;
  padding: 7px 16px; cursor: pointer; font-size: 13px; }
.sf-tab.active { background: var(--brand); border-color: var(--brand); color: #fff; }
.inline-msg { margin: 0 0 10px; font-size: 13px; padding: 8px 10px; border-radius: 6px;
  background: #fff; border: 1px solid var(--border); }
.inline-msg.ok-text { color: #067647; border-color: #abefc6; background: #f6fef9; }
.inline-msg.error-text { color: #b42318; border-color: #fda29b; background: #fffbfa; }
.sf-cols { display: flex; gap: 14px; flex-wrap: wrap; align-items: flex-start; }
.sf-panel { background: #fff; border: 1px solid var(--border); border-radius: 8px;
  padding: 12px 14px; margin-bottom: 14px; min-width: 320px; flex: 1;
  display: flex; flex-direction: column; gap: 8px; }
.sf-panel.wide { min-width: 100%; }
.sf-panel h3 { margin: 0; font-size: 14px; }
.sf-panel .btn { align-self: flex-start; margin-top: 4px; }
select { padding: 5px 8px; border: 1px solid var(--border); border-radius: 6px; font-size: 13px; }
h3 { font-size: 14px; margin: 14px 0 8px; }
</style>
