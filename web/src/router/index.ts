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
    { path: '/resumes',   component: () => import('../views/ResumesView.vue') },
    { path: '/interviews', component: () => import('../views/InterviewsView.vue') },
    { path: '/messages',    component: () => import('../views/MessagingView.vue') },
    { path: '/contacts',    redirect: '/messages' },
    { path: '/references',  component: () => import('../views/ReferencesView.vue') },
    { path: '/digest',     component: () => import('../views/DigestView.vue') },
    { path: '/salary-calculator', component: () => import('../views/SalaryCalculatorView.vue') },
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
        { path: 'connections', component: () => import('../views/settings/ConnectionsSettingsView.vue') },
        { path: 'fine-tune',   component: () => import('../views/settings/FineTuneView.vue') },
        { path: 'license',     component: () => import('../views/settings/LicenseView.vue') },
        { path: 'data',        component: () => import('../views/settings/DataView.vue') },
        { path: 'privacy',     component: () => import('../views/settings/PrivacyView.vue') },
        { path: 'developer',   component: () => import('../views/settings/DeveloperView.vue') },
      ],
    },
    // AI profile assistant, reachable both during onboarding (linked from the
    // resume step's "AI Assistant" tab) and afterward as a settings entry
    // point, so it's exempt from the wizard-completion gate below.
    { path: '/wizard/ai-profile', component: () => import('../views/wizard/WizardAIView.vue') },
    // Onboarding flow: full-page layout, no AppNav
    {
      path: '/setup',
      component: () => import('../views/wizard/OnboardingFlow.vue'),
    },
    { path: '/wizard/setup-path', component: () => import('../views/wizard/SetupPathChoiceView.vue') },
    // Legacy linear wizard, kept reachable directly, unlinked from the Hub.
    // Not deleted in this phase; see the plan's Global Constraints.
    {
      path: '/setup/legacy',
      component: () => import('../views/wizard/WizardLayout.vue'),
      children: [
        // No `redirect` here on purpose: a static redirect resolves before
        // WizardLayout ever mounts, which made its own resume-at-last-step
        // logic (onMounted checking route.path === '/setup/legacy')
        // permanently unreachable — bare /setup/legacy always silently
        // landed fresh visitors on step 1 regardless of real progress.
        // Render the hardware step here as a same-content fallback;
        // WizardLayout's onMounted still owns routing to the real resume
        // point once loadStatus() resolves.
        { path: '',           component: () => import('../views/wizard/WizardHardwareStep.vue') },
        { path: 'hardware',   component: () => import('../views/wizard/WizardHardwareStep.vue') },
        { path: 'tier',       component: () => import('../views/wizard/WizardTierStep.vue') },
        { path: 'resume',     component: () => import('../views/wizard/WizardResumeStep.vue') },
        { path: 'training',   component: () => import('../views/wizard/WizardTrainingStep.vue') },
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

  // Demo mode: pre-seeded data, no wizard needed — route freely
  if (config.isDemo) return next()

  // Wizard gate runs first for every route except /setup itself, the AI
  // profile assistant (reachable both during and after onboarding), and
  // /settings/* (the Hub links onboarding users into Settings pages before
  // wizardComplete, e.g. to fill in Profile/Resume/Search).
  if (
    !to.path.startsWith('/setup') &&
    to.path !== '/wizard/ai-profile' &&
    to.path !== '/wizard/setup-path' &&
    !to.path.startsWith('/settings/') &&
    !config.wizardComplete
  ) {
    return next('/setup')
  }

  // /setup routes: let wizardGuard handle complete→redirect-to-home logic
  if (to.path.startsWith('/setup')) return wizardGuard(to, _from, next)

  // Settings tier-gating (runs on every /settings/* navigation, regardless of
  // whether the wizard/onboarding hub has been completed)
  if (to.path.startsWith('/settings/')) return settingsGuard(to, _from, next)

  next()
})
