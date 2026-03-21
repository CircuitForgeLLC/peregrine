import { createRouter, createWebHistory } from 'vue-router'
import { useAppConfigStore } from '../stores/appConfig'

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

router.beforeEach((to, _from, next) => {
  if (!to.path.startsWith('/settings/')) return next()
  const config = useAppConfigStore()
  const tab = to.path.replace('/settings/', '')
  const devOverride = localStorage.getItem('dev_tier_override')
  const gpuProfiles = ['single-gpu', 'dual-gpu']

  if (tab === 'system' && config.isCloud) return next('/settings/my-profile')
  if (tab === 'fine-tune') {
    const cloudBlocked = config.isCloud && config.tier !== 'premium'
    const selfHostedBlocked = !config.isCloud && !gpuProfiles.includes(config.inferenceProfile)
    if (cloudBlocked || selfHostedBlocked) return next('/settings/my-profile')
  }
  if (tab === 'developer' && !config.isDevMode && !devOverride) return next('/settings/my-profile')
  next()
})
