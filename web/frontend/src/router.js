import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    redirect: '/accounts'
  },
  {
    path: '/accounts',
    name: 'Accounts',
    component: () => import('./views/AccountsView.vue')
  },
  {
    path: '/browsers',
    name: 'Browsers',
    component: () => import('./views/BrowsersView.vue')
  },
  {
    path: '/tasks',
    name: 'Tasks',
    component: () => import('./views/TasksView.vue')
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
