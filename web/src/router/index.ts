import { createRouter, createWebHistory } from 'vue-router'
import { useAppConfigStore } from '../stores/appConfig'
import { settingsGuard } from './settingsGuard'
import { wizardGuard } from './wizardGuard'

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
    // Onboarding wizard — full-page layout, no AppNav
    {
      path: '/setup',
      component: () => import('../views/wizard/WizardLayout.vue'),
      children: [
        { path: '',           redirect: '/setup/hardware' },
        { path: 'hardware',   component: () => import('../views/wizard/WizardHardwareStep.vue') },
        { path: 'tier',       component: () => import('../views/wizard/WizardTierStep.vue') },
        { path: 'resume',     component: () => import('../views/wizard/WizardResumeStep.vue') },
        { path: 'identity',   component: () => import('../views/wizard/WizardIdentityStep.vue') },
        { path: 'inference',  component: () => import('../views/wizard/WizardInferenceStep.vue') },
        { path: 'search',     component: () => import('../views/wizard/WizardSearchStep.vue') },
        { path: 'integrations', component: () => import('../views/wizard/WizardIntegrationsStep.vue') },
      ],
    },
    // Catch-all — FastAPI serves index.html for all unknown routes (SPA mode)
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach(async (to, _from, next) => {
  const config = useAppConfigStore()
  if (!config.loaded) await config.load()

  // Wizard gate runs first for every route except /setup itself
  if (!to.path.startsWith('/setup') && !config.wizardComplete) {
    return next('/setup')
  }

  // /setup routes: let wizardGuard handle complete→redirect-to-home logic
  if (to.path.startsWith('/setup')) return wizardGuard(to, _from, next)

  // Settings tier-gating (runs only when wizard is complete)
  if (to.path.startsWith('/settings/')) return settingsGuard(to, _from, next)

  next()
})
