<script setup>
import { RouterLink, RouterView } from 'vue-router'
import { useWebSocket } from './stores/websocket'

const ws = useWebSocket()
ws.connect()
</script>

<template>
  <div class="min-h-screen bg-gray-100">
    <!-- 导航栏 -->
    <nav class="bg-white shadow-sm">
      <div class="max-w-7xl mx-auto px-4">
        <div class="flex justify-between h-16">
          <div class="flex">
            <div class="flex-shrink-0 flex items-center">
              <span class="text-xl font-bold text-gray-800">Auto BitBrowser</span>
            </div>
            <div class="hidden sm:ml-6 sm:flex sm:space-x-8">
              <RouterLink
                to="/accounts"
                class="inline-flex items-center px-1 pt-1 border-b-2 text-sm font-medium"
                :class="$route.path === '/accounts' ? 'border-blue-500 text-gray-900' : 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700'"
              >
                账号管理
              </RouterLink>
              <RouterLink
                to="/browsers"
                class="inline-flex items-center px-1 pt-1 border-b-2 text-sm font-medium"
                :class="$route.path === '/browsers' ? 'border-blue-500 text-gray-900' : 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700'"
              >
                浏览器窗口
              </RouterLink>
              <RouterLink
                to="/tasks"
                class="inline-flex items-center px-1 pt-1 border-b-2 text-sm font-medium"
                :class="$route.path === '/tasks' ? 'border-blue-500 text-gray-900' : 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700'"
              >
                任务执行
              </RouterLink>
            </div>
          </div>
          <div class="flex items-center">
            <span
              class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium"
              :class="ws.connected ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'"
            >
              {{ ws.connected ? '已连接' : '未连接' }}
            </span>
          </div>
        </div>
      </div>
    </nav>

    <!-- 主内容区 -->
    <main class="max-w-7xl mx-auto py-6 px-4 sm:px-6 lg:px-8">
      <RouterView />
    </main>
  </div>
</template>
