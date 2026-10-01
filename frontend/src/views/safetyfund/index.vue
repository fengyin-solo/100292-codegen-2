<template>
  <section class="page" data-module="safetyfund">
    <header class="page-head">
      <div>
        <h2>安全费用台账</h2>
        <p class="page-desc">
          按项目与年度管理安全生产费用的提取与使用：应提金额只按现行已发布口径计算，
          使用与提取分账登记，余额实时核对；口径调整后旧台账按当时比例留存。
        </p>
      </div>
    </header>

    <!-- 身份切换：用于演示“只有本项目安全员可登记、跨单位当场驳回” -->
    <div class="form-card">
      <div class="form-grid">
        <label>
          <span>当前操作人（安全员身份）</span>
          <select :value="store.user.工号" @change="switchUser(($event.target as HTMLSelectElement).value)">
            <option v-for="officer in meta.officers" :key="officer.工号" :value="officer.工号">
              {{ officer.工号 }} · {{ officer.姓名 }}（{{ officer.单位 }}）
            </option>
          </select>
        </label>
        <span class="page-desc">
          负责项目：{{ assignedProjects(store.user.工号) || '无（外部人员，登记使用会被当场驳回）' }}
        </span>
        <span v-if="meta.current_version" class="tag blue">
          现行提取口径：{{ meta.current_version }}
        </span>
      </div>
    </div>

    <nav class="tabs">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="tab-btn"
        :class="{ active: activeTab === tab.key }"
        type="button"
        @click="switchTab(tab.key)"
      >
        {{ tab.label }}
      </button>
    </nav>

    <p v-if="notice.text" class="notice" :class="notice.ok ? 'ok' : 'fail'">{{ notice.text }}</p>

    <!-- 一、项目台账 -->
    <div v-if="activeTab === 'ledger'">
      <form class="filter-bar" @submit.prevent="loadLedger">
        <label class="filter-item">
          <span>项目</span>
          <select v-model="ledgerFilter.project">
            <option value="">全部项目</option>
            <option v-for="p in meta.projects" :key="p.项目编号" :value="p.项目编号">
              {{ p.项目编号 }} {{ p.项目名称 }}
            </option>
          </select>
        </label>
        <label class="filter-item">
          <span>年度</span>
          <input v-model="ledgerFilter.year" placeholder="如 2025，留空查全部" />
        </label>
        <button class="btn" type="submit">查询</button>
      </form>
      <table class="data-table">
        <thead>
          <tr>
            <th>项目编号</th><th>项目名称</th><th>所属单位</th><th>年度</th>
            <th>口径版本</th><th>计提基数</th><th>提取比例</th>
            <th>应提（已提）</th><th>已使用</th><th>可用余额</th><th>最近提取</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in ledger.items" :key="`${row.项目编号}-${row.年度}`">
            <td>{{ row.项目编号 }}</td>
            <td>{{ row.项目名称 }}</td>
            <td>{{ row.所属单位 }}</td>
            <td>{{ row.年度 }}</td>
            <td><span class="tag blue">{{ row.口径版本 }}</span></td>
            <td class="num">{{ money(row.计提基数 ?? 0) }}</td>
            <td>{{ percent(Number(row.提取比例)) }}</td>
            <td class="num">{{ money(row.应提金额 ?? 0) }}</td>
            <td class="num">{{ money(row.已用金额 ?? 0) }}</td>
            <td class="num"><strong>{{ money(row.可用余额 ?? 0) }}</strong></td>
            <td>{{ row.最近提取日期 }}</td>
          </tr>
          <tr v-if="!ledger.items.length">
            <td colspan="11" class="empty-state">暂无现行提取台账，请先到「提取登记」登记</td>
          </tr>
        </tbody>
        <tfoot v-if="ledger.items.length">
          <tr>
            <td colspan="7"><strong>合计</strong></td>
            <td class="num"><strong>{{ money(ledger.合计.应提金额) }}</strong></td>
            <td class="num"><strong>{{ money(ledger.合计.已用金额) }}</strong></td>
            <td class="num"><strong>{{ money(ledger.合计.可用余额) }}</strong></td>
            <td></td>
          </tr>
        </tfoot>
      </table>
    </div>

    <!-- 二、提取登记（含历史台账） -->
    <div v-if="activeTab === 'accrual'">
      <div class="form-card">
        <p class="section-title">登记年度提取（应提金额 = 计提基数 × 现行口径比例，自动计算）</p>
        <form class="form-grid" @submit.prevent="submitAccrual">
          <label>
            <span>项目</span>
            <select v-model="accrualForm.项目编号" required>
              <option value="" disabled>请选择项目</option>
              <option v-for="p in meta.projects" :key="p.项目编号" :value="p.项目编号">
                {{ p.项目编号 }} {{ p.项目名称 }}
              </option>
            </select>
          </label>
          <label>
            <span>年度</span>
            <input v-model.number="accrualForm.年度" type="number" placeholder="如 2025" required />
          </label>
          <label>
            <span>计提基数（元）</span>
            <input v-model.number="accrualForm.计提基数" type="number" min="0" step="0.01" placeholder="年度安全费用计提基数" required />
          </label>
          <label>
            <span>登记人工号</span>
            <input v-model="accrualForm.登记人工号" readonly />
          </label>
          <button class="btn primary" type="submit">登记提取</button>
          <span class="page-desc">比例取自现行口径 {{ meta.current_version }}，不可手工改比例；同项目同年度重复登记只认第一次。</span>
        </form>
      </div>

      <div class="filter-bar">
        <button class="btn" :class="{ primary: !accrualHistory }" type="button" @click="accrualHistory = false; loadAccruals()">
          现行提取（{{ accrualHistory ? '' : accrualTotal }}）
        </button>
        <button class="btn" :class="{ primary: accrualHistory }" type="button" @click="accrualHistory = true; loadAccruals()">
          历史台账（按当时口径保留）
        </button>
      </div>
      <table class="data-table">
        <thead>
          <tr>
            <th>流水</th><th>项目编号</th><th>项目名称</th><th>年度</th><th>口径版本</th>
            <th>计提基数</th><th>提取比例</th><th>应提金额</th><th>登记日期</th><th>登记人</th><th>备注</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in accruals" :key="String(row.id)">
            <td>{{ row.id }}</td>
            <td>{{ row.项目编号 }}</td>
            <td>{{ row.项目名称 }}</td>
            <td>{{ row.年度 }}</td>
            <td>
              <span class="tag" :class="row.历史 ? 'gray' : 'blue'">{{ row.口径版本 }}</span>
            </td>
            <td class="num">{{ money(row.计提基数 ?? 0) }}</td>
            <td>{{ percent(Number(row.提取比例)) }}</td>
            <td class="num">{{ money(row.应提金额 ?? 0) }}</td>
            <td>{{ row.登记日期 }}</td>
            <td>{{ row.登记人工号 }}</td>
            <td>{{ row.备注 || '—' }}</td>
          </tr>
          <tr v-if="!accruals.length">
            <td colspan="11" class="empty-state">暂无{{ accrualHistory ? '历史' : '现行' }}提取记录</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 三、使用登记 -->
    <div v-if="activeTab === 'usage'">
      <div class="form-card">
        <p class="section-title">登记安全费用使用（独立于提取账；超出已提余额、发票重复、非本项目安全员均不落账）</p>
        <form class="form-grid" @submit.prevent="submitUsage">
          <label>
            <span>项目</span>
            <select v-model="usageForm.项目编号" required>
              <option value="" disabled>请选择项目</option>
              <option v-for="p in meta.projects" :key="p.项目编号" :value="p.项目编号">
                {{ p.项目编号 }} {{ p.项目名称 }}（{{ p.所属单位 }}）
              </option>
            </select>
          </label>
          <label>
            <span>年度</span>
            <input v-model.number="usageForm.年度" type="number" placeholder="如 2025" required />
          </label>
          <label>
            <span>费用类别</span>
            <select v-model="usageForm.费用类别" required>
              <option value="" disabled>请选择类别</option>
              <option v-for="cat in meta.expense_categories" :key="cat" :value="cat">{{ cat }}</option>
            </select>
          </label>
          <label>
            <span>金额（元）</span>
            <input v-model.number="usageForm.金额" type="number" min="0.01" step="0.01" required />
          </label>
          <label>
            <span>发票号</span>
            <input v-model="usageForm.发票号" placeholder="全库唯一，重复报销只生效一次" required />
          </label>
          <label class="form-grid-wide">
            <span>用途说明</span>
            <input class="wide" v-model="usageForm.用途说明" required />
          </label>
          <label>
            <span>登记人工号</span>
            <input v-model="usageForm.登记人工号" readonly />
          </label>
          <button class="btn primary" type="submit">提交使用登记</button>
        </form>
        <p v-if="usageBalance" class="page-desc" style="margin-top:8px">
          当前项目年度余额（与台账页同源）：已提 {{ money(usageBalance.已提金额) }}，
          已用 {{ money(usageBalance.已用金额) }}，可用余额 {{ money(usageBalance.可用余额) }}
        </p>
      </div>

      <form class="filter-bar" @submit.prevent="loadUsages">
        <label class="filter-item">
          <span>项目</span>
          <select v-model="usageFilter.project">
            <option value="">全部项目</option>
            <option v-for="p in meta.projects" :key="p.项目编号" :value="p.项目编号">{{ p.项目编号 }}</option>
          </select>
        </label>
        <label class="filter-item">
          <span>年度</span>
          <input v-model="usageFilter.year" placeholder="年度" />
        </label>
        <label class="filter-item">
          <span>发票号/用途</span>
          <input v-model="usageFilter.关键字" placeholder="关键字检索" />
        </label>
        <button class="btn" type="submit">查询</button>
      </form>

      <div class="stat-row">
        <article class="stat-card">
          <span class="stat-label">使用笔数</span>
          <strong class="stat-value">{{ usageData.total }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">合计金额（随单笔登记实时重算）</span>
          <strong class="stat-value">{{ money(usageData.合计金额) }}</strong>
        </article>
      </div>
      <table class="data-table">
        <thead>
          <tr>
            <th>流水</th><th>项目</th><th>年度</th><th>费用类别</th><th>金额</th>
            <th>发票号</th><th>用途说明</th><th>登记日期</th><th>登记人</th><th>登记人单位</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in usageData.items" :key="String(row.id)">
            <td>{{ row.id }}</td>
            <td>{{ row.项目编号 }}</td>
            <td>{{ row.年度 }}</td>
            <td>{{ row.费用类别 }}</td>
            <td class="num">{{ money(row.金额 ?? 0) }}</td>
            <td>{{ row.发票号 }}</td>
            <td>{{ row.用途说明 }}</td>
            <td>{{ row.登记日期 }}</td>
            <td>{{ row.登记人工号 }} {{ row.登记人姓名 }}</td>
            <td>{{ row.登记人单位 }}</td>
          </tr>
          <tr v-if="!usageData.items.length">
            <td colspan="10" class="empty-state">暂无使用明细</td>
          </tr>
        </tbody>
      </table>
      <p v-if="usageData.按类别合计?.length" class="page-desc" style="margin-top:8px">
        按类别合计：
        <span v-for="(item, idx) in usageData.按类别合计" :key="item.费用类别">
          {{ item.费用类别 }} {{ money(item.金额) }}<span v-if="idx < usageData.按类别合计.length - 1">；</span>
        </span>
      </p>
    </div>

    <!-- 四、口径管理 -->
    <div v-if="activeTab === 'version'">
      <div class="form-card">
        <p class="section-title">登记新版提取口径（先存草稿，发布后才作为提取依据）</p>
        <form class="form-grid" @submit.prevent="submitVersion">
          <label>
            <span>版本编号</span>
            <input v-model="versionForm.版本编号" placeholder="如 V2027" required />
          </label>
          <label>
            <span>版本名称</span>
            <input v-model="versionForm.版本名称" placeholder="如 安全生产费用口径2027版" />
          </label>
          <label>
            <span>生效年度</span>
            <input v-model.number="versionForm.生效年度" type="number" required />
          </label>
          <p
            v-for="(_rate, idx) in versionForm.rates"
            :key="idx"
            class="form-grid"
            style="width:100%; margin:0"
          >
            <label>
              <span>项目类别</span>
              <input v-model="versionForm.rates[idx].项目类别" placeholder="如 建筑施工" />
            </label>
            <label>
              <span>提取比例（小数，0.025 = 2.5%）</span>
              <input v-model.number="versionForm.rates[idx].提取比例" type="number" step="0.001" min="0" max="1" />
            </label>
            <button class="btn ghost" type="button" @click="versionForm.rates.splice(idx, 1)">删除该行</button>
          </p>
          <button class="btn" type="button" @click="versionForm.rates.push({ 项目类别: '', 提取比例: 0 })">
            + 增加类别比例
          </button>
          <button class="btn primary" type="submit">存为草稿</button>
        </form>
      </div>

      <div class="form-card">
        <p class="section-title">口径调整后的存量重填</p>
        <form class="form-grid" @submit.prevent="submitRefill">
          <label>
            <span>重填年度（留空 = 全部现行提取记录）</span>
            <input v-model.number="refillYear" type="number" placeholder="如 2025" />
          </label>
          <button class="btn primary" type="button" @click="submitRefill">按现行口径 {{ meta.current_version }} 重填</button>
          <span class="page-desc">旧版记录转为历史台账、按当时比例原样保留；已是现行口径的记录自动跳过。</span>
        </form>
      </div>

      <table class="data-table">
        <thead>
          <tr>
            <th>版本编号</th><th>版本名称</th><th>生效年度</th><th>状态</th>
            <th>各类别提取比例</th><th>发布日期</th><th>说明</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="v in versions" :key="v.版本编号">
            <td>{{ v.版本编号 }}</td>
            <td>{{ v.版本名称 }}</td>
            <td>{{ v.生效年度 }}</td>
            <td>
              <span v-if="v.是否现行" class="tag green">现行</span>
              <span v-else-if="v.状态 === '已发布'" class="tag gray">已发布（历史版本）</span>
              <span v-else class="tag gray">草稿</span>
            </td>
            <td>
              <span v-for="r in v.提取比例明细" :key="r.项目类别" style="margin-right:10px; white-space:nowrap">
                {{ r.项目类别 }} {{ percent(r.提取比例) }}
              </span>
            </td>
            <td>{{ v.发布日期 || '—' }}</td>
            <td>{{ v.发布说明 || '—' }}</td>
            <td>
              <button v-if="v.状态 === '草稿'" class="link" type="button" @click="publishVersion(v.id)">
                发布为现行口径
              </button>
              <span v-else class="page-desc">—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <footer class="page-foot">
      <span>安全费用台账 · 提取与使用分账登记 · 所有金额以元为单位保留两位小数</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Row = Record<string, string | number | null>

interface Officer { 工号: string; 姓名: string; 单位: string; 负责项目: string[] }
interface Project { 项目编号: string; 项目名称: string; 所属单位: string; 项目类别: string }
interface Meta {
  officers: Officer[]
  projects: Project[]
  expense_categories: string[]
  current_version: string | null
  current_rates: { 项目类别: string; 提取比例: number }[]
}

const store = useSessionStore()
const tabs = [
  { key: 'ledger', label: '项目台账' },
  { key: 'accrual', label: '提取登记' },
  { key: 'usage', label: '使用登记' },
  { key: 'version', label: '口径管理' },
] as const
type TabKey = (typeof tabs)[number]['key']
const activeTab = ref<TabKey>('ledger')

const meta = reactive<Meta>({
  officers: [],
  projects: [],
  expense_categories: [],
  current_version: null,
  current_rates: [],
})

const notice = ref<{ text: string; ok: boolean }>({ text: '', ok: true })
function flash(text: string, ok: boolean) {
  notice.value = { text, ok }
}

function money(value: number | string | null | undefined): string {
  const n = Number(value ?? 0)
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function percent(rate: number | string): string {
  return `${(Number(rate) * 100).toString()}%`
}
function assignedProjects(officerNo: string): string {
  const officer = meta.officers.find((item) => item.工号 === officerNo)
  return officer && officer.负责项目.length ? officer.负责项目.join('、') : ''
}

async function postJson(path: string, body: object): Promise<{ ok: boolean; message: string; entry: Record<string, unknown> | null }> {
  const response = await request(path, { method: 'POST', body: JSON.stringify(body) })
  return response.json()
}

// ---------- 身份 ----------
function switchUser(officerNo: string) {
  const officer = meta.officers.find((item) => item.工号 === officerNo)
  if (officer) {
    store.setUser({ 工号: officer.工号, 姓名: officer.姓名, 单位: officer.单位 })
    accrualForm.登记人工号 = officer.工号
    usageForm.登记人工号 = officer.工号
  }
}

// ---------- 项目台账 ----------
const ledgerFilter = reactive<{ project: string; year: string }>({ project: '', year: '' })
const ledger = ref<{
  items: Row[]
  total: number
  合计: { 应提金额: number; 已用金额: number; 可用余额: number }
}>({ items: [], total: 0, 合计: { 应提金额: 0, 已用金额: 0, 可用余额: 0 } })

async function loadLedger() {
  const params = new URLSearchParams()
  if (ledgerFilter.project) params.set('项目编号', ledgerFilter.project)
  if (ledgerFilter.year) params.set('年度', ledgerFilter.year)
  const response = await request(`/api/safetyfund/ledger?${params.toString()}`)
  if (response.ok) ledger.value = await response.json()
}

// ---------- 提取登记 ----------
const accruals = ref<Row[]>([])
const accrualHistory = ref(false)
const accrualTotal = ref(0)
const accrualForm = reactive({
  项目编号: '',
  年度: new Date().getFullYear(),
  计提基数: undefined as number | undefined,
  登记人工号: store.user.工号,
  备注: '',
})

async function loadAccruals() {
  const response = await request(`/api/safetyfund/accruals?历史=${accrualHistory.value}`)
  if (response.ok) {
    const payload = await response.json()
    accruals.value = payload.items
    accrualTotal.value = payload.total
  }
}

async function submitAccrual() {
  notice.value.text = ''
  const result = await postJson('/api/safetyfund/accruals', { ...accrualForm })
  flash(result.message, result.ok)
  if (result.ok) {
    accrualForm.计提基数 = undefined
    await Promise.all([loadAccruals(), loadLedger(), refreshUsageBalance()])
  }
}

// ---------- 使用登记 ----------
const usageForm = reactive({
  项目编号: '',
  年度: new Date().getFullYear(),
  费用类别: '',
  金额: undefined as number | undefined,
  发票号: '',
  用途说明: '',
  登记人工号: store.user.工号,
})
const usageFilter = reactive<{ project: string; year: string; 关键字: string }>({
  project: '',
  year: '',
  关键字: '',
})
const usageData = ref<{
  items: Row[]
  total: number
  合计金额: number
  按类别合计: { 费用类别: string; 金额: number }[]
}>({ items: [], total: 0, 合计金额: 0, 按类别合计: [] })

const usageBalance = ref<{ 已提金额: number; 已用金额: number; 可用余额: number } | null>(null)

async function refreshUsageBalance() {
  usageBalance.value = null
  if (!usageForm.项目编号 || !usageForm.年度) return
  const params = new URLSearchParams({ 项目编号: usageForm.项目编号, 年度: String(usageForm.年度) })
  const response = await request(`/api/safetyfund/ledger?${params.toString()}`)
  if (response.ok) {
    const payload = await response.json()
    const hit = payload.items.find(
      (item: Row) => item.项目编号 === usageForm.项目编号 && Number(item.年度) === Number(usageForm.年度),
    )
    if (hit) {
      usageBalance.value = {
        已提金额: Number(hit.应提金额),
        已用金额: Number(hit.已用金额),
        可用余额: Number(hit.可用余额),
      }
    }
  }
}
watch(() => [usageForm.项目编号, usageForm.年度], refreshUsageBalance)

async function loadUsages() {
  const params = new URLSearchParams()
  if (usageFilter.project) params.set('项目编号', usageFilter.project)
  if (usageFilter.year) params.set('年度', usageFilter.year)
  if (usageFilter.关键字) params.set('关键字', usageFilter.关键字)
  const response = await request(`/api/safetyfund/usages?${params.toString()}`)
  if (response.ok) usageData.value = await response.json()
}

async function submitUsage() {
  notice.value.text = ''
  const result = await postJson('/api/safetyfund/usages', { ...usageForm })
  flash(result.message, result.ok)
  if (result.ok) {
    usageForm.金额 = undefined
    usageForm.发票号 = ''
    usageForm.用途说明 = ''
    await Promise.all([loadUsages(), loadLedger(), refreshUsageBalance()])
  }
}

// ---------- 口径管理 ----------
interface VersionRow {
  id: number
  版本编号: string
  版本名称: string
  生效年度: number
  状态: string
  是否现行: boolean
  发布日期: string
  发布说明: string
  提取比例明细: { 项目类别: string; 提取比例: number }[]
}
const versions = ref<VersionRow[]>([])
const versionForm = reactive<{
  版本编号: string
  版本名称: string
  生效年度: number | undefined
  rates: { 项目类别: string; 提取比例: number }[]
}>({
  版本编号: '',
  版本名称: '',
  生效年度: undefined,
  rates: [
    { 项目类别: '建筑施工', 提取比例: 0 },
    { 项目类别: '安装工程', 提取比例: 0 },
    { 项目类别: '机械制造', 提取比例: 0 },
  ],
})
const refillYear = ref<number | undefined>(undefined)

async function loadVersions() {
  const response = await request('/api/safetyfund/versions')
  if (response.ok) {
    const payload = await response.json()
    versions.value = payload.items
  }
}

async function submitVersion() {
  notice.value.text = ''
  const rates = versionForm.rates.filter((item) => item.项目类别.trim() !== '')
  const result = await postJson('/api/safetyfund/versions', {
    版本编号: versionForm.版本编号,
    版本名称: versionForm.版本名称,
    生效年度: versionForm.生效年度,
    rates,
  })
  flash(result.message, result.ok)
  if (result.ok) {
    versionForm.版本编号 = ''
    versionForm.版本名称 = ''
    versionForm.生效年度 = undefined
    await Promise.all([loadVersions(), loadMeta()])
  }
}

async function publishVersion(id: number) {
  notice.value.text = ''
  const result = await postJson(`/api/safetyfund/versions/${id}/publish`, {})
  flash(result.message, result.ok)
  if (result.ok) await Promise.all([loadVersions(), loadMeta()])
}

async function submitRefill() {
  notice.value.text = ''
  const result = await postJson('/api/safetyfund/accruals/refill', {
    年度: refillYear.value ?? null,
    登记人工号: store.user.工号,
  })
  flash(result.message, result.ok)
  if (result.ok) {
    await Promise.all([loadAccruals(), loadLedger(), refreshUsageBalance()])
  }
}

// ---------- 初始化 ----------
async function loadMeta() {
  const response = await request('/api/safetyfund/meta')
  if (response.ok) {
    const payload = (await response.json()) as Meta
    Object.assign(meta, payload)
    const current = meta.officers.find((item) => item.工号 === store.user.工号) ?? meta.officers[0]
    if (current) {
      store.setUser({ 工号: current.工号, 姓名: current.姓名, 单位: current.单位 })
      accrualForm.登记人工号 = current.工号
      usageForm.登记人工号 = current.工号
    }
  }
}

function switchTab(key: TabKey) {
  activeTab.value = key
  notice.value.text = ''
  if (key === 'ledger') void loadLedger()
  if (key === 'accrual') void loadAccruals()
  if (key === 'usage') void loadUsages()
  if (key === 'version') void loadVersions()
}

onMounted(async () => {
  await loadMeta()
  await Promise.all([loadLedger(), loadAccruals(), loadUsages(), loadVersions(), refreshUsageBalance()])
})
</script>
