import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { useApiFetch } from '../composables/useApi'

export interface ActiveTask {
  id: number
  task_type: string
  job_id: number
  status: 'running' | 'queued'
}

export const TASK_LABEL: Record<string, string> = {
  cover_letter:        'Cover letter',
  company_research:    'Research',
  discovery:           'Discovery',
  enrich_descriptions: 'Enriching descriptions',
  score:               'Scoring matches',
  scrape_url:          'Scraping listing',
  email_sync:          'Email sync',
  wizard_generate:     'Wizard',
  prepare_training:    'Training data',
}

/**
 * Ordered pipeline stages — tasks are visually grouped under discovery
 * when they appear together, showing users the full auto-chain.
 */
export const DISCOVERY_PIPELINE = ['discovery', 'enrich_descriptions', 'score'] as const

/** Group active tasks into pipeline groups for display.
 *  Non-pipeline tasks (cover_letter, email_sync, etc.) each form their own group.
 */
export interface TaskGroup {
  primary: ActiveTask
  steps:   ActiveTask[]  // pipeline children, empty for non-pipeline tasks
}

export function groupTasks(tasks: ActiveTask[]): TaskGroup[] {
  const pipelineSet = new Set(DISCOVERY_PIPELINE as readonly string[])
  const pipelineTasks = tasks.filter(t => pipelineSet.has(t.task_type))
  const otherTasks    = tasks.filter(t => !pipelineSet.has(t.task_type))

  const groups: TaskGroup[] = []

  // Build one discovery pipeline group from all pipeline tasks in order
  if (pipelineTasks.length) {
    const ordered = [...DISCOVERY_PIPELINE]
      .map(type => pipelineTasks.find(t => t.task_type === type))
      .filter(Boolean) as ActiveTask[]
    groups.push({ primary: ordered[0], steps: ordered.slice(1) })
  }

  // Each non-pipeline task is its own group
  for (const task of otherTasks) {
    groups.push({ primary: task, steps: [] })
  }

  return groups
}

export const useTasksStore = defineStore('tasks', () => {
  const tasks  = ref<ActiveTask[]>([])
  const count  = computed(() => tasks.value.length)
  const groups = computed(() => groupTasks(tasks.value))
  const label  = computed(() => {
    if (!tasks.value.length) return ''
    const first = tasks.value[0]
    const name  = TASK_LABEL[first.task_type] ?? first.task_type
    return tasks.value.length === 1 ? name : `${name} +${tasks.value.length - 1}`
  })

  // Callback registered by views that want counts refreshed while tasks run
  let _onTasksClear: (() => void) | null = null
  let _tasksWereActive = false

  function onTasksClear(cb: () => void) { _onTasksClear = cb }

  let _timer: ReturnType<typeof setInterval> | null = null

  async function poll() {
    const { data } = await useApiFetch<{ count: number; tasks: ActiveTask[] }>('/api/tasks/active')
    if (!data) return
    const wasActive = _tasksWereActive
    tasks.value = data.tasks
    _tasksWereActive = data.tasks.length > 0
    // Fire callback when task queue just cleared so counts can update
    if (wasActive && !_tasksWereActive && _onTasksClear) _onTasksClear()
  }

  function startPolling() {
    if (_timer) return
    poll()
    _timer = setInterval(poll, 4000)
  }

  function stopPolling() {
    if (_timer) { clearInterval(_timer); _timer = null }
  }

  return { tasks, count, groups, label, poll, startPolling, stopPolling, onTasksClear }
})
