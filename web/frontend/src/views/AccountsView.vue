<script setup>
import { ref, onMounted, computed } from 'vue'
import { accountsApi } from '../api'

const accounts = ref([])
const stats = ref({})
const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const searchQuery = ref('')
const statusFilter = ref('')
const showImportModal = ref(false)
const importContent = ref('')
const showEditModal = ref(false)
const editForm = ref({
  email: '',
  password: '',
  recovery_email: '',
  secret_key: '',
  status: 'pending',
  message: '',
})

const statusOptions = [
  { value: '', label: '全部' },
  { value: 'pending', label: '待处理' },
  { value: 'link_ready', label: '有链接' },
  { value: 'verified', label: '已验证' },
  { value: 'subscribed', label: '已订阅' },
  { value: 'ineligible', label: '无资格' },
  { value: 'error', label: '错误' },
]
const editStatusOptions = statusOptions.filter((opt) => opt.value)

const statusColors = {
  pending: 'bg-gray-100 text-gray-800',
  link_ready: 'bg-yellow-100 text-yellow-800',
  verified: 'bg-blue-100 text-blue-800',
  subscribed: 'bg-green-100 text-green-800',
  ineligible: 'bg-red-100 text-red-800',
  error: 'bg-red-100 text-red-800',
}

const totalPages = computed(() => Math.ceil(total.value / pageSize.value))

async function loadAccounts() {
  loading.value = true
  try {
    const params = {
      page: page.value,
      page_size: pageSize.value,
    }
    if (searchQuery.value) params.search = searchQuery.value
    if (statusFilter.value) params.status = statusFilter.value

    const res = await accountsApi.list(params)
    accounts.value = res.data.items
    total.value = res.data.total
  } catch (e) {
    console.error('加载账号失败:', e)
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  try {
    const res = await accountsApi.stats()
    stats.value = res.data
  } catch (e) {
    console.error('加载统计失败:', e)
  }
}

async function deleteAccount(email) {
  if (!confirm(`确定要删除账号 ${email} 吗？`)) return
  try {
    await accountsApi.delete(email)
    await loadAccounts()
    await loadStats()
  } catch (e) {
    alert('删除失败: ' + e.message)
  }
}

async function handleImport() {
  if (!importContent.value.trim()) return
  try {
    const res = await accountsApi.import({
      content: importContent.value,
      separator: '----',
    })
    alert(`成功导入 ${res.data.imported} 个账号`)
    showImportModal.value = false
    importContent.value = ''
    await loadAccounts()
    await loadStats()
  } catch (e) {
    alert('导入失败: ' + e.message)
  }
}

function openEdit(acc) {
  editForm.value = {
    email: acc.email || '',
    password: acc.password || '',
    recovery_email: acc.recovery_email || '',
    secret_key: acc.secret_key || '',
    status: acc.status || 'pending',
    message: acc.message || '',
  }
  showEditModal.value = true
}

async function saveEdit() {
  if (!editForm.value.email) return
  try {
    await accountsApi.update(editForm.value.email, {
      password: editForm.value.password,
      recovery_email: editForm.value.recovery_email,
      secret_key: editForm.value.secret_key,
      status: editForm.value.status,
      message: editForm.value.message,
    })
    showEditModal.value = false
    await loadAccounts()
    await loadStats()
  } catch (e) {
    alert('更新失败: ' + e.message)
  }
}

async function handleExport() {
  try {
    const res = await accountsApi.export(statusFilter.value || null)
    const blob = new Blob([res.data.content], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'accounts_export.txt'
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    alert('导出失败: ' + e.message)
  }
}

function handleSearch() {
  page.value = 1
  loadAccounts()
}

function handlePageChange(newPage) {
  page.value = newPage
  loadAccounts()
}

onMounted(() => {
  loadAccounts()
  loadStats()
})
</script>

<template>
  <div>
    <!-- 统计卡片 -->
    <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4 mb-6">
      <div class="bg-white rounded-lg shadow p-4">
        <div class="text-2xl font-bold text-gray-900">{{ stats.total || 0 }}</div>
        <div class="text-sm text-gray-500">总账号</div>
      </div>
      <div class="bg-white rounded-lg shadow p-4">
        <div class="text-2xl font-bold text-gray-600">{{ stats.pending || 0 }}</div>
        <div class="text-sm text-gray-500">待处理</div>
      </div>
      <div class="bg-white rounded-lg shadow p-4">
        <div class="text-2xl font-bold text-yellow-600">{{ stats.link_ready || 0 }}</div>
        <div class="text-sm text-gray-500">有链接</div>
      </div>
      <div class="bg-white rounded-lg shadow p-4">
        <div class="text-2xl font-bold text-blue-600">{{ stats.verified || 0 }}</div>
        <div class="text-sm text-gray-500">已验证</div>
      </div>
      <div class="bg-white rounded-lg shadow p-4">
        <div class="text-2xl font-bold text-green-600">{{ stats.subscribed || 0 }}</div>
        <div class="text-sm text-gray-500">已订阅</div>
      </div>
      <div class="bg-white rounded-lg shadow p-4">
        <div class="text-2xl font-bold text-red-600">{{ stats.ineligible || 0 }}</div>
        <div class="text-sm text-gray-500">无资格</div>
      </div>
      <div class="bg-white rounded-lg shadow p-4">
        <div class="text-2xl font-bold text-purple-600">{{ stats.with_browser || 0 }}</div>
        <div class="text-sm text-gray-500">有窗口</div>
      </div>
    </div>

    <!-- 工具栏 -->
    <div class="bg-white rounded-lg shadow mb-6 p-4">
      <div class="flex flex-wrap items-center gap-4">
        <input
          v-model="searchQuery"
          type="text"
          placeholder="搜索邮箱..."
          class="flex-1 min-w-[200px] px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          @keyup.enter="handleSearch"
        />
        <select
          v-model="statusFilter"
          class="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          @change="handleSearch"
        >
          <option v-for="opt in statusOptions" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </option>
        </select>
        <button
          @click="handleSearch"
          class="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
        >
          搜索
        </button>
        <button
          @click="showImportModal = true"
          class="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700"
        >
          导入
        </button>
        <button
          @click="handleExport"
          class="px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700"
        >
          导出
        </button>
      </div>
    </div>

    <!-- 账号列表 -->
    <div class="bg-white rounded-lg shadow overflow-hidden">
      <table class="min-w-full divide-y divide-gray-200">
        <thead class="bg-gray-50">
          <tr>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">邮箱</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">状态</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">浏览器</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">更新时间</th>
            <th class="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">操作</th>
          </tr>
        </thead>
        <tbody class="bg-white divide-y divide-gray-200">
          <tr v-if="loading">
            <td colspan="5" class="px-6 py-4 text-center text-gray-500">加载中...</td>
          </tr>
          <tr v-else-if="accounts.length === 0">
            <td colspan="5" class="px-6 py-4 text-center text-gray-500">暂无数据</td>
          </tr>
          <tr v-for="acc in accounts" :key="acc.email" class="hover:bg-gray-50">
            <td class="px-6 py-4 whitespace-nowrap">
              <div class="text-sm font-medium text-gray-900">{{ acc.email }}</div>
              <div class="text-sm text-gray-500" v-if="acc.recovery_email">{{ acc.recovery_email }}</div>
            </td>
            <td class="px-6 py-4 whitespace-nowrap">
              <span
                class="inline-flex px-2 py-1 text-xs font-semibold rounded-full"
                :class="statusColors[acc.status] || 'bg-gray-100 text-gray-800'"
              >
                {{ acc.status }}
              </span>
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
              <span v-if="acc.browser_id" class="text-green-600">{{ acc.browser_id.slice(0, 8) }}...</span>
              <span v-else class="text-gray-400">无</span>
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
              {{ acc.updated_at || '-' }}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
              <button
                @click="openEdit(acc)"
                class="text-blue-600 hover:text-blue-900 mr-4"
              >
                编辑
              </button>
              <button
                @click="deleteAccount(acc.email)"
                class="text-red-600 hover:text-red-900"
              >
                删除
              </button>
            </td>
          </tr>
        </tbody>
      </table>

      <!-- 分页 -->
      <div class="bg-gray-50 px-4 py-3 flex items-center justify-between border-t border-gray-200 sm:px-6">
        <div class="text-sm text-gray-700">
          共 {{ total }} 条记录
        </div>
        <div class="flex space-x-2">
          <button
            v-for="p in totalPages"
            :key="p"
            @click="handlePageChange(p)"
            class="px-3 py-1 rounded"
            :class="p === page ? 'bg-blue-600 text-white' : 'bg-white text-gray-700 hover:bg-gray-100'"
          >
            {{ p }}
          </button>
        </div>
      </div>
    </div>

    <!-- 导入弹窗 -->
    <div v-if="showImportModal" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg shadow-xl w-full max-w-2xl p-6">
        <h3 class="text-lg font-medium text-gray-900 mb-4">批量导入账号</h3>
        <p class="text-sm text-gray-500 mb-4">格式：邮箱----密码----辅助邮箱----2FA密钥（或空格分隔，每行一个）</p>
        <textarea
          v-model="importContent"
          rows="10"
          class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          placeholder="example@gmail.com----password----recovery@gmail.com----2FASECRET"
        ></textarea>
        <div class="mt-4 flex justify-end space-x-4">
          <button
            @click="showImportModal = false"
            class="px-4 py-2 text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200"
          >
            取消
          </button>
          <button
            @click="handleImport"
            class="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
          >
            导入
          </button>
        </div>
      </div>
    </div>

    <!-- 编辑弹窗 -->
    <div v-if="showEditModal" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg shadow-xl w-full max-w-lg p-6">
        <h3 class="text-lg font-medium text-gray-900 mb-4">编辑账号</h3>
        <div class="space-y-3">
          <div>
            <label class="block text-sm text-gray-700 mb-1">邮箱</label>
            <input
              v-model="editForm.email"
              type="text"
              disabled
              class="w-full px-3 py-2 border border-gray-300 rounded-md bg-gray-100 text-sm"
            />
          </div>
          <div>
            <label class="block text-sm text-gray-700 mb-1">密码</label>
            <input
              v-model="editForm.password"
              type="text"
              class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label class="block text-sm text-gray-700 mb-1">辅助邮箱</label>
            <input
              v-model="editForm.recovery_email"
              type="text"
              class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label class="block text-sm text-gray-700 mb-1">2FA 密钥</label>
            <input
              v-model="editForm.secret_key"
              type="text"
              class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label class="block text-sm text-gray-700 mb-1">状态</label>
            <select
              v-model="editForm.status"
              class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option v-for="opt in editStatusOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
          </div>
          <div>
            <label class="block text-sm text-gray-700 mb-1">备注</label>
            <input
              v-model="editForm.message"
              type="text"
              class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        </div>
        <div class="mt-4 flex justify-end space-x-4">
          <button
            @click="showEditModal = false"
            class="px-4 py-2 text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200"
          >
            取消
          </button>
          <button
            @click="saveEdit"
            class="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
          >
            保存
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
