import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import PipelineStepper from '../PipelineStepper.vue'
import { useInterviewsStore, type PipelineJob } from '../../stores/interviews'

function makeRouter() {
  return createRouter({ history: createWebHistory(), routes: [{ path: '/:p*', component: { template: '<div/>' } }] })
}

function factory() {
  return mount(PipelineStepper, { global: { plugins: [makeRouter()] } })
}

function job(overrides: Partial<PipelineJob>): PipelineJob {
  return {
    id: 1, title: 'Engineer', company: 'Acme', url: null, location: null, is_remote: false,
    salary: null, match_score: null, keyword_gaps: null, status: 'applied',
    interview_date: null, rejection_stage: null, applied_at: null, phone_screen_at: null,
    interviewing_at: null, offer_at: null, hired_at: null, survey_at: null,
    hired_feedback: null, stage_signals: [],
    ...overrides,
  }
}

describe('PipelineStepper', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('renders all six linear stages, excluding interview_rejected', () => {
    const w = factory()
    expect(w.text()).toContain('Applied')
    expect(w.text()).toContain('Survey')
    expect(w.text()).toContain('Phone Screen')
    expect(w.text()).toContain('Interviewing')
    expect(w.text()).toContain('Offer')
    expect(w.text()).toContain('Hired')
    expect(w.text()).not.toContain('Rejected —')
    expect(w.findAll('.pipeline-stage')).toHaveLength(6)
  })

  it('counts jobs per stage', () => {
    const store = useInterviewsStore()
    store.jobs = [
      job({ id: 1, status: 'applied' }),
      job({ id: 2, status: 'applied' }),
      job({ id: 3, status: 'offer' }),
    ]
    const w = factory()
    const stages = w.findAll('.pipeline-stage')
    const applied = stages.find(s => s.text().includes('Applied'))
    const offer = stages.find(s => s.text().includes('Offer'))
    const hired = stages.find(s => s.text().includes('Hired'))
    expect(applied?.text()).toContain('2')
    expect(offer?.text()).toContain('1')
    expect(hired?.text()).toContain('0')
  })

  it('marks a stage active only when it has at least one job', () => {
    const store = useInterviewsStore()
    store.jobs = [job({ id: 1, status: 'interviewing' })]
    const w = factory()
    const stages = w.findAll('.pipeline-stage')
    const interviewing = stages.find(s => s.text().includes('Interviewing'))
    const applied = stages.find(s => s.text().includes('Applied'))
    expect(interviewing?.classes()).toContain('pipeline-stage--active')
    expect(applied?.classes()).not.toContain('pipeline-stage--active')
  })

  it('shows a rejected summary line when there are rejected jobs', () => {
    const store = useInterviewsStore()
    store.jobs = [
      job({ id: 1, status: 'interview_rejected' }),
      job({ id: 2, status: 'interview_rejected' }),
    ]
    const w = factory()
    expect(w.text()).toContain('2 rejected')
  })

  it('hides the rejected summary line when there are none', () => {
    const store = useInterviewsStore()
    store.jobs = [job({ id: 1, status: 'applied' })]
    const w = factory()
    expect(w.find('.pipeline-stepper__rejected').exists()).toBe(false)
  })

  it('links to the full interviews board', () => {
    const w = factory()
    const link = w.find('a[href="/interviews"]')
    expect(link.exists()).toBe(true)
    expect(link.text()).toContain('View all interviews')
  })
})
