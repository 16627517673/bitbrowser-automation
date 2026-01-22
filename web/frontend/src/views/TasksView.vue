<script setup>
import { ref, computed, onMounted } from 'vue'
import { accountsApi, tasksApi, configApi } from '../api'
import { useWebSocket } from '../stores/websocket'

const ws = useWebSocket()

const accounts = ref([])
const selectedEmails = ref([])
const selectedTaskTypes = ref(['setup_2fa'])
const closeAfter = ref(false)
const concurrency = ref(1)
const loading = ref(false)
const submitting = ref(false)

// 配置相关
const configLoading = ref(false)
const configSaving = ref(false)
const showConfig = ref(false)  // 折叠配置
const config = ref({
  sheerid_api_key: '',
  card_number: '',
  card_exp_month: '',
  card_exp_year: '',
  card_cvv: '',
  card_zip: '',
})

const taskTypes = [
  { value: 'setup_2fa', label: '设置 2FA' },
  { value: 'reset_2fa', label: '修改 2FA' },
  { value: 'age_verification', label: '年龄验证' },
  { value: 'get_sheerlink', label: '获取 SheerLink' },
  { value: 'bind_card', label: '绑卡订阅' },
]

const selectAll = computed({
  get: () => selectedEmails.value.length === accounts.value.length && accounts.value.length > 0,
  set: (val) => {
    selectedEmails.value = val ? accounts.value.map(a => a.email) : []
  }
})

const currentProgress = computed(() => ws.taskProgress)
const isRunning = computed(() => currentProgress.value?.status === 'running')
const accountsProgress = computed(() => Object.values(ws.accountsProgress))

const progressStats = computed(() => {
  const progress = accountsProgress.value
  const total = currentProgress.value?.total ?? progress.length
  const completed = progress.filter(p => p.status === 'completed').length
  const failed = progress.filter(p => p.status === 'failed').length
  const running = progress.filter(p => p.status === 'running').length
  const pending = Math.max(total - completed - failed - running, 0)
  return { total, completed, failed, running, pending }
})

async function loadAccounts() {
  loading.value = true
  try {
    const res = await accountsApi.list({ page: 1, page_size: 100 })
    accounts.value = res.data.items
  } catch (e) {
    console.error('加载账号失败:', e)
  } finally {
    loading.value = false
  }
}

async function submitTask() {
  if (selectedEmails.value.length === 0) {
    alert('请至少选择一个账号')
    return
  }
  if (selectedTaskTypes.value.length === 0) {
    alert('请至少选择一个任务类型')
    return
  }
  ws.clearAccountsProgress()
  submitting.value = true
  try {
    const res = await tasksApi.create({
      task_types: selectedTaskTypes.value,
      emails: selectedEmails.value,
      close_after: closeAfter.value,
      concurrency: concurrency.value,
    })
    alert(`任务已创建: ${res.data.task_id}`)
  } catch (e) {
    alert('创建任务失败: ' + e.message)
  } finally {
    submitting.value = false
  }
}

function getStatusClass(status) {
  const classes = {
    pending: 'bg-gray-100 text-gray-800',
    link_ready: 'bg-yellow-100 text-yellow-800',
    verified: 'bg-blue-100 text-blue-800',
    subscribed: 'bg-green-100 text-green-800',
    ineligible: 'bg-red-100 text-red-800',
    error: 'bg-red-100 text-red-800',
  }
  return classes[status] || 'bg-gray-100 text-gray-800'
}

function getAccountProgressClass(status) {
  const classes = {
    pending: 'border-gray-300 bg-gray-50',
    running: 'border-blue-400 bg-blue-50',
    completed: 'border-green-400 bg-green-50',
    failed: 'border-red-400 bg-red-50',
  }
  return classes[status] || 'border-gray-300 bg-gray-50'
}

function getAccountStatusIcon(status) {
  const icons = {
    pending: '⏳',
    running: '🔄',
    completed: '✅',
    failed: '❌',
  }
  return icons[status] || '⏳'
}

onMounted(() => {
  loadAccounts()
  loadConfig()
})

async function loadConfig() {
  configLoading.value = true
  try {
    const res = await configApi.get()
    config.value = res.data
  } catch (e) {
    console.error('加载配置失败:', e)
  } finally {
    configLoading.value = false
  }
}

async function saveConfig() {
  configSaving.value = true
  try {
    await configApi.update(config.value)
    alert('配置已保存')
  } catch (e) {
    alert('保存配置失败: ' + e.message)
  } finally {
    configSaving.value = false
  }
}
</script>

<template>
  <div class="space-y-4">
    <!-- 顶部：任务配置区（横向布局） -->
    <div class="bg-white rounded-lg shadow p-4">
      <div class="flex flex-wrap items-center gap-4">
        <!-- 任务类型选择 -->
        <div class="flex-1 min-w-[300px]">
          <div class="flex flex-wrap gap-2">
            <label
              v-for="type in taskTypes"
              :key="type.value"
              class="flex items-center px-3 py-1.5 rounded-lg border cursor-pointer text-sm"
              :class="selectedTaskTypes.includes(type.value) ? 'border-blue-500 bg-blue-50 text-blue-700' : 'border-gray-200 hover:border-gray-300'"
            >
              <input
                type="checkbox"
                :value="type.value"
                v-model="selectedTaskTypes"
                class="h-4 w-4 text-blue-600 rounded border-gray-300 mr-2"
              />
              <span>{{ type.label }}</span>
            </label>
          </div>
        </div>

        <!-- 执行选项 -->
        <div class="flex items-center gap-4">
          <div class="flex items-center gap-2">
            <span class="text-sm text-gray-600">并发:</span>
            <input
              type="range"
              v-model.number="concurrency"
              min="1"
              max="5"
              step="1"
              class="w-20 h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer"
            />
            <span class="text-sm font-medium text-gray-900 w-4">{{ concurrency }}</span>
          </div>
          <label class="flex items-center">
            <input
              type="checkbox"
              v-model="closeAfter"
              class="h-4 w-4 text-blue-600 rounded border-gray-300"
            />
            <span class="ml-2 text-sm text-gray-700">完成后关闭</span>
          </label>
          <button
            @click="showConfig = !showConfig"
            class="px-3 py-1.5 text-sm text-gray-600 border border-gray-300 rounded-md hover:bg-gray-50"
          >
            ⚙️ 配置
          </button>
          <button
            @click="submitTask"
            :disabled="submitting || isRunning || selectedEmails.length === 0"
            class="px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
          >
            {{ submitting ? '提交中...' : isRunning ? '执行中...' : `开始执行 (${selectedEmails.length})` }}
          </button>
        </div>
      </div>

      <!-- 配置面板（可折叠） -->
      <div v-if="showConfig" class="mt-4 pt-4 border-t border-gray-200">
        <div v-if="configLoading" class="text-center text-gray-500 py-2">加载中...</div>
        <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <div>
            <label class="block text-xs font-medium text-gray-700 mb-1">SheerID API Key</label>
            <input
              type="text"
              v-model="config.sheerid_api_key"
              placeholder="API Key"
              class="w-full px-2 py-1.5 border border-gray-300 rounded text-sm"
            />
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-700 mb-1">卡号</label>
            <input
              type="text"
              v-model="config.card_number"
              placeholder="卡号"
              class="w-full px-2 py-1.5 border border-gray-300 rounded text-sm"
            />
          </div>
          <div class="grid grid-cols-3 gap-2">
            <div>
              <label class="block text-xs font-medium text-gray-700 mb-1">月</label>
              <input type="text" v-model="config.card_exp_month" placeholder="MM" maxlength="2" class="w-full px-2 py-1.5 border border-gray-300 rounded text-sm" />
            </div>
            <div>
              <label class="block text-xs font-medium text-gray-700 mb-1">年</label>
              <input type="text" v-model="config.card_exp_year" placeholder="YY" maxlength="2" class="w-full px-2 py-1.5 border border-gray-300 rounded text-sm" />
            </div>
            <div>
              <label class="block text-xs font-medium text-gray-700 mb-1">CVV</label>
              <input type="text" v-model="config.card_cvv" placeholder="CVV" maxlength="4" class="w-full px-2 py-1.5 border border-gray-300 rounded text-sm" />
            </div>
          </div>
          <div class="flex items-end gap-2">
            <div class="flex-1">
              <label class="block text-xs font-medium text-gray-700 mb-1">ZIP</label>
              <input type="text" v-model="config.card_zip" placeholder="邮编" class="w-full px-2 py-1.5 border border-gray-300 rounded text-sm" />
            </div>
            <button
              @click="saveConfig"
              :disabled="configSaving"
              class="px-3 py-1.5 bg-green-600 text-white rounded text-sm hover:bg-green-700 disabled:opacity-50"
            >
              {{ configSaving ? '...' : '保存' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 主内容区：左右两栏 -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <!-- 左侧：账号选择 -->
      <div class="bg-white rounded-lg shadow">
        <div class="px-4 py-3 border-b border-gray-200">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-4">
              <h3 class="text-base font-medium text-gray-900">选择账号</h3>
              <label class="flex items-center">
                <input type="checkbox" v-model="selectAll" class="h-4 w-4 text-blue-600 rounded border-gray-300" />
                <span class="ml-2 text-sm text-gray-600">全选</span>
              </label>
            </div>
            <span class="text-sm text-gray-500">{{ selectedEmails.length }} / {{ accounts.length }}</span>
          </div>
        </div>
        <div class="p-2 max-h-[500px] overflow-y-auto">
          <div v-if="loading" class="text-center text-gray-500 py-4">加载中...</div>
          <div v-else-if="accounts.length === 0" class="text-center text-gray-500 py-4">暂无账号</div>
          <label
            v-for="acc in accounts"
            :key="acc.email"
            class="flex items-center px-2 py-1.5 rounded hover:bg-gray-50 cursor-pointer"
          >
            <input
              type="checkbox"
              :value="acc.email"
              v-model="selectedEmails"
              class="h-4 w-4 text-blue-600 rounded border-gray-300"
            />
            <span class="ml-3 flex-1 min-w-0 text-sm text-gray-900 truncate">{{ acc.email }}</span>
            <span class="ml-2 px-1.5 py-0.5 text-xs rounded-full shrink-0" :class="getStatusClass(acc.status)">
              {{ acc.status }}
            </span>
            <span v-if="acc.browser_id" class="ml-1 text-xs text-green-600 shrink-0">✓</span>
          </label>
        </div>
      </div>

      <!-- 右侧：进度和日志 -->
      <div class="space-y-4">
        <!-- 任务进度 -->
        <div v-if="currentProgress || accountsProgress.length > 0" class="bg-white rounded-lg shadow p-4">
          <div class="flex items-center justify-between mb-3">
            <h3 class="text-base font-medium text-gray-900">任务进度</h3>
            <div v-if="currentProgress" class="text-sm">
              <span class="font-medium" :class="{
                'text-yellow-600': currentProgress.status === 'running',
                'text-green-600': currentProgress.status === 'completed',
                'text-red-600': currentProgress.status === 'failed',
              }">{{ currentProgress.status }}</span>
              <span class="text-gray-500 ml-2">{{ currentProgress.completed }}/{{ currentProgress.total }}</span>
            </div>
          </div>

          <!-- 进度条 -->
          <div class="w-full bg-gray-200 rounded-full h-2 overflow-hidden flex mb-3">
            <div class="bg-green-500 h-2 transition-all" :style="{ width: progressStats.total ? `${(progressStats.completed / progressStats.total) * 100}%` : '0%' }"></div>
            <div class="bg-red-500 h-2 transition-all" :style="{ width: progressStats.total ? `${(progressStats.failed / progressStats.total) * 100}%` : '0%' }"></div>
          </div>

          <!-- 账号进度列表 -->
          <div v-if="accountsProgress.length > 0" class="max-h-[200px] overflow-y-auto space-y-1">
            <div
              v-for="acc in accountsProgress"
              :key="acc.email"
              class="p-2 rounded border text-sm"
              :class="getAccountProgressClass(acc.status)"
            >
              <div class="flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <span>{{ getAccountStatusIcon(acc.status) }}</span>
                  <span class="font-medium truncate max-w-[180px]" :title="acc.email">{{ acc.email.split('@')[0] }}</span>
                </div>
                <span v-if="acc.currentTask" class="text-xs text-gray-600">{{ acc.currentTask }}</span>
              </div>
              <div v-if="acc.message && acc.status === 'failed'" class="text-xs text-red-600 mt-1 truncate">{{ acc.message }}</div>
            </div>
          </div>
        </div>

        <!-- 实时日志 -->
        <div class="bg-white rounded-lg shadow p-4">
          <div class="flex items-center justify-between mb-3">
            <h3 class="text-base font-medium text-gray-900">实时日志</h3>
            <button @click="ws.clearLogs()" class="text-xs text-gray-500 hover:text-gray-700">清空</button>
          </div>
          <div class="max-h-[280px] overflow-y-auto space-y-0.5 font-mono text-xs bg-gray-50 rounded p-2">
            <div v-if="ws.logs.length === 0" class="text-gray-400 py-2 text-center">暂无日志</div>
            <div
              v-for="(log, index) in ws.logs"
              :key="index"
              class="flex"
              :class="{
                'text-red-600': log.level === 'error',
                'text-yellow-600': log.level === 'warning',
                'text-gray-600': log.level === 'info',
              }"
            >
              <span class="text-gray-400 mr-2 shrink-0">{{ log.time }}</span>
              <span v-if="log.email" class="text-blue-600 mr-1 shrink-0">[{{ log.email.split('@')[0] }}]</span>
              <span class="break-all">{{ log.message }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
