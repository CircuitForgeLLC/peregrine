import { createRouter, createWebHistory } from 'vue-router'
import { useAppConfigStore } from '../stores/appConfig'
import { settingsGuard } from './settingsGuard'

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
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
    { path: '/survey/:id', component: () => import('../views/SurveyView.vue') },
    {
      path: '/settings',
      component: () => import('../views/settings/SettingsView.vue'),
      redirect: '/settings/my-profile',
      children: [
        { path: 'my-profile',  component: () => import('../views/settings/MyProfileView.vue') },
        { path: 'resume',      component: () => import('../views/settings/ResumeProfileView.vue') },
        { path: 'search',      component: () => import('../views/settings/SearchPrefsView.vue') },
        { path: 'system',      component: () => import('../views/settings/SystemSettingsView.vue') },
        { path: 'fine-tune',   component: () => import('../views/settings/FineTuneView.vue') },
        { path: 'license',     component: () => import('../views/settings/LicenseView.vue') },
        { path: 'data',        component: () => import('../views/settings/DataView.vue') },
        { path: 'privacy',     component: () => import('../views/settings/PrivacyView.vue') },
        { path: 'developer',   component: () => import('../views/settings/DeveloperView.vue') },
      ],
    },
    // Catch-all — FastAPI serves index.html for all unknown routes (SPA mode)
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach(async (to, _from, next) => {
  if (!to.path.startsWith('/settings/')) return next()
  const config = useAppConfigStore()
  if (!config.loaded) await config.load()
  settingsGuard(to, _from, next)
})
