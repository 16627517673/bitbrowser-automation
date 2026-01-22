<script setup>
import { ref, onMounted } from 'vue'
import { browsersApi } from '../api'

const browsers = ref([])
const loading = ref(false)
const syncing = ref(false)

async function loadBrowsers() {
  loading.value = true
  try {
    const res = await browsersApi.list()
    browsers.value = res.data
  } catch (e) {
    console.error('加载浏览器列表失败:', e)
    if (e.response?.status === 503) {
      alert('无法连接到比特浏览器 API，请确保比特浏览器已启动')
    }
  } finally {
    loading.value = false
  }
}

async function syncBrowsers() {
  syncing.value = true
  try {
    const res = await browsersApi.sync()
    alert(`同步完成，共 ${res.data.synced} 个窗口`)
    await loadBrowsers()
  } catch (e) {
    alert('同步失败: ' + e.message)
  } finally {
    syncing.value = false
  }
}

async function openBrowser(id) {
  try {
    await browsersApi.open(id)
  } catch (e) {
    alert('打开失败: ' + e.message)
  }
}

async function deleteBrowser(id) {
  if (!confirm('确定要删除此浏览器窗口吗？配置将保留用于恢复。')) return
  try {
    await browsersApi.delete(id, true)
    await loadBrowsers()
  } catch (e) {
    alert('删除失败: ' + e.message)
  }
}

async function restoreBrowser(email) {
  try {
    const res = await browsersApi.restore(email)
    alert(`恢复成功: ${res.data.browser_id}`)
    await loadBrowsers()
  } catch (e) {
    alert('恢复失败: ' + e.message)
  }
}

onMounted(() => {
  loadBrowsers()
})
</script>

<template>
  <div>
    <!-- 工具栏 -->
    <div class="bg-white rounded-lg shadow mb-6 p-4">
      <div class="flex items-center justify-between">
        <h2 class="text-lg font-medium text-gray-900">浏览器窗口管理</h2>
        <div class="flex space-x-4">
          <button
            @click="loadBrowsers"
            :disabled="loading"
            class="px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700 disabled:opacity-50"
          >
            {{ loading ? '加载中...' : '刷新' }}
          </button>
          <button
            @click="syncBrowsers"
            :disabled="syncing"
            class="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
          >
            {{ syncing ? '同步中...' : '同步到数据库' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 浏览器列表 -->
    <div class="bg-white rounded-lg shadow overflow-hidden">
      <table class="min-w-full divide-y divide-gray-200">
        <thead class="bg-gray-50">
          <tr>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">序号</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">窗口 ID</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">关联账号</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">分组</th>
            <th class="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">操作</th>
          </tr>
        </thead>
        <tbody class="bg-white divide-y divide-gray-200">
          <tr v-if="loading">
            <td colspan="5" class="px-6 py-4 text-center text-gray-500">加载中...</td>
          </tr>
          <tr v-else-if="browsers.length === 0">
            <td colspan="5" class="px-6 py-4 text-center text-gray-500">暂无浏览器窗口</td>
          </tr>
          <tr v-for="(browser, index) in browsers" :key="browser.id" class="hover:bg-gray-50">
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
              {{ browser.seq || index + 1 }}
            </td>
            <td class="px-6 py-4 whitespace-nowrap">
              <div class="text-sm font-medium text-gray-900">{{ browser.id }}</div>
              <div class="text-sm text-gray-500" v-if="browser.name">{{ browser.name }}</div>
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
              {{ browser.userName || '-' }}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
              {{ browser.groupName || '默认' }}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-right text-sm font-medium space-x-2">
              <button
                @click="openBrowser(browser.id)"
                class="text-blue-600 hover:text-blue-900"
              >
                打开
              </button>
              <button
                @click="deleteBrowser(browser.id)"
                class="text-red-600 hover:text-red-900"
              >
                删除
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 提示信息 -->
    <div class="mt-6 bg-yellow-50 border border-yellow-200 rounded-lg p-4">
      <h3 class="text-sm font-medium text-yellow-800">提示</h3>
      <ul class="mt-2 text-sm text-yellow-700 list-disc list-inside">
        <li>删除窗口后配置会保留在数据库中，可在账号管理页面恢复</li>
        <li>同步功能会将比特浏览器中的窗口配置保存到数据库</li>
        <li>确保比特浏览器已启动且 API 可访问（默认 127.0.0.1:54345）</li>
      </ul>
    </div>
  </div>
</template>
