import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import MobileTaskPill from './MobileTaskPill.vue'
import { useTasksStore } from '../stores/tasks'

// Regression test: this pill used to live inside TaskIndicator.vue, nested
// in AppNav's .app-sidebar -- a display:none ancestor on mobile hid it
// regardless of its own position:fixed styling, so it never actually
// rendered there. Moved to its own component, mounted as a sibling of the
// mobile tab bar instead. A unit test can't catch "hidden by an ancestor"
// (jsdom doesn't compute layout), but it does lock in that the component
// itself renders correctly from live store state.
describe('MobileTaskPill', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('renders nothing when there are no active tasks', () => {
    const wrapper = mount(MobileTaskPill)
    expect(wrapper.find('.mobile-task-pill').exists()).toBe(false)
  })

  it('shows the pill with a label and count when tasks are active', () => {
    const store = useTasksStore()
    store.tasks = [{ id: 1, task_type: 'discovery', job_id: 0, status: 'running' }]
    const wrapper = mount(MobileTaskPill)
    expect(wrapper.find('.mobile-task-pill').exists()).toBe(true)
    expect(wrapper.text()).toContain('Discovery')
    expect(wrapper.find('.mobile-task-pill__badge').text()).toBe('1')
  })

  it('updates when the shared task store changes (same store TaskIndicator polls)', async () => {
    const store = useTasksStore()
    const wrapper = mount(MobileTaskPill)
    expect(wrapper.find('.mobile-task-pill').exists()).toBe(false)

    store.tasks = [
      { id: 1, task_type: 'discovery', job_id: 0, status: 'running' },
      { id: 2, task_type: 'score', job_id: 0, status: 'queued' },
    ]
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.mobile-task-pill__badge').text()).toBe('2')
  })
})
