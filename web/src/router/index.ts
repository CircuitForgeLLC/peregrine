import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/',           component: () => import('../views/HomeView.vue') },
    { path: '/review',     component: () => import('../views/JobReviewView.vue') },
    { path: '/apply',      component: () => import('../views/ApplyView.vue') },
    { path: '/apply/:id', component: () => import('../views/ApplyWorkspaceView.vue') },
    { path: '/interviews', component: () => import('../views/InterviewsView.vue') },
    { path: '/digest',     component: () => import('../views/DigestView.vue') },
    { path: '/prep',       component: () => import('../views/InterviewPrepView.vue') },
    { path: '/prep/:id',   component: () => import('../views/InterviewPrepView.vue') },
    { path: '/survey',     component: () => import('../views/SurveyView.vue') },
    { path: '/settings',   component: () => import('../views/SettingsView.vue') },
    // Catch-all — FastAPI serves index.html for all unknown routes (SPA mode)
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
