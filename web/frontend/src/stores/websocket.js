import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useWebSocket = defineStore('websocket', () => {
  const connected = ref(false)
  const logs = ref([])
  const taskProgress = ref(null)
  const accountsProgress = ref({})  // 新增：每个账号的独立进度 {email -> progress}
  let ws = null
  let reconnectTimer = null

  function connect() {
    if (ws && ws.readyState === WebSocket.OPEN) return

    ws = new WebSocket('ws://localhost:8000/ws')

    ws.onopen = () => {
      connected.value = true
      console.log('[WS] 已连接')
      // 心跳
      setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send('ping')
        }
      }, 30000)
    }

    ws.onclose = () => {
      connected.value = false
      console.log('[WS] 已断开')
      // 自动重连
      reconnectTimer = setTimeout(connect, 3000)
    }

    ws.onerror = (err) => {
      console.error('[WS] 错误:', err)
    }

    ws.onmessage = (event) => {
      if (event.data === 'pong') return

      try {
        const msg = JSON.parse(event.data)
        handleMessage(msg)
      } catch (e) {
        console.error('[WS] 解析消息失败:', e)
      }
    }
  }

  function handleMessage(msg) {
    if (msg.type === 'task_progress') {
      taskProgress.value = msg.data
      // 任务完成或失败时，清理账号进度
      if (msg.data.status === 'completed' || msg.data.status === 'failed') {
        // 延迟清理，让用户能看到最终状态
        setTimeout(() => {
          accountsProgress.value = {}
        }, 5000)
      }
    } else if (msg.type === 'account_progress') {
      // 新增：处理单个账号的进度
      const data = msg.data
      accountsProgress.value = {
        ...accountsProgress.value,
        [data.email]: {
          email: data.email,
          status: data.status,
          currentTask: data.current_task,
          message: data.message,
          total: data.total,
          completed: data.completed,
          failed: data.failed,
        }
      }
    } else if (msg.type === 'log') {
      logs.value.unshift({
        ...msg.data,
        time: new Date().toLocaleTimeString(),
      })
      // 保留最近 100 条
      if (logs.value.length > 100) {
        logs.value = logs.value.slice(0, 100)
      }
    }
  }

  function disconnect() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
    }
    if (ws) {
      ws.close()
    }
  }

  function clearLogs() {
    logs.value = []
  }

  function clearAccountsProgress() {
    accountsProgress.value = {}
  }

  return {
    connected,
    logs,
    taskProgress,
    accountsProgress,
    connect,
    disconnect,
    clearLogs,
    clearAccountsProgress,
  }
})
