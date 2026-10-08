import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'home',
    component: () => import('../views/HomeView.vue'),
  },
  {
    path: '/setup',
    name: 'setup',
    component: () => import('../views/SetupView.vue'),
  },
  {
    path: '/studio/:id',
    name: 'studio',
    component: () => import('../views/StudioView.vue'),
    props: true,
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
