<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useSearchStore } from '../stores/settings/search'
import { useApiFetch } from '../composables/useApi'
import {
  formatCurrency,
  hasSalaryRange,
  salaryCountLine,
  salaryRolesLine,
  SALARY_EMPTY_STATE_TEXT,
  type SalaryStats,
} from '../composables/useSalaryStats'

const search = useSearchStore()

const titlesInput = ref('')
const locationInput = ref('')

const loading = ref(true)
const errored = ref(false)
const stats = ref<SalaryStats | null>(null)

// Position the median marker within the p25–p75 bar as a percentage.
function medianPosition(): number {
  if (!stats.value) return 50
  const { p25, p75, median } = stats.value
  if (p25 == null || p75 == null || median == null || p75 <= p25) return 50
  const pct = ((median - p25) / (p75 - p25)) * 100
  return Math.min(100, Math.max(0, pct))
}

async function fetchStats() {
  loading.value = true
  errored.value = false
  const params = new URLSearchParams()
  if (titlesInput.value.trim()) params.set('titles', titlesInput.value.trim())
  if (locationInput.value.trim()) params.set('location', locationInput.value.trim())
  const qs = params.toString()
  const { data, error } = await useApiFetch<SalaryStats>(`/api/salary-stats${qs ? `?${qs}` : ''}`)
  if (error || !data) {
    errored.value = true
  } else {
    stats.value = data
  }
  loading.value = false
}

async function recalculate() {
  await fetchStats()
}

onMounted(async () => {
  await search.load()
  titlesInput.value = search.job_titles.join(', ')
  locationInput.value = search.locations[0] ?? ''
  await fetchStats()
})
</script>

<template>
  <div class="salary-calculator">
    <h1 class="salary-calculator__title">Salary Calculator</h1>

    <p class="salary-calculator__framing">
      Based on job postings matching your search — not a broader market benchmark.
      Peregrine only looks at the roles in your own search results, so this reflects
      what you're seeing, not the wider job market.
    </p>

    <form class="salary-calculator__form" @submit.prevent="recalculate">
      <div class="salary-calculator__field">
        <label for="salary-titles">Job titles</label>
        <input
          id="salary-titles"
          v-model="titlesInput"
          type="text"
          placeholder="e.g. Software Engineer, Backend Developer"
        />
      </div>
      <div class="salary-calculator__field">
        <label for="salary-location">Location</label>
        <input
          id="salary-location"
          v-model="locationInput"
          type="text"
          placeholder="e.g. Remote, Boston MA"
        />
      </div>
      <button type="submit" class="salary-calculator__recalculate" :disabled="loading">
        Recalculate
      </button>
    </form>

    <p v-if="loading" class="salary-calculator__loading">Loading your search results…</p>

    <p v-else-if="errored" class="salary-calculator__error">
      Couldn't load salary data right now.
    </p>

    <template v-else-if="stats">
      <p class="salary-calculator__count">
        {{ salaryRolesLine(stats) }}
      </p>

      <template v-if="hasSalaryRange(stats)">
        <div class="salary-calculator__bar-wrap">
          <div class="salary-calculator__bar" role="img"
            :aria-label="`Salary range from ${formatCurrency(stats.p25!)} to ${formatCurrency(stats.p75!)}, median ${formatCurrency(stats.median ?? 0)}`">
            <div
              v-if="stats.median != null"
              class="salary-calculator__bar-marker"
              :style="{ left: medianPosition() + '%' }"
            />
          </div>
          <div class="salary-calculator__bar-labels">
            <span class="salary-calculator__bar-label salary-calculator__bar-label--low">
              {{ formatCurrency(stats.p25!) }}
            </span>
            <span v-if="stats.median != null" class="salary-calculator__bar-label salary-calculator__bar-label--median">
              Median {{ formatCurrency(stats.median) }}
            </span>
            <span class="salary-calculator__bar-label salary-calculator__bar-label--high">
              {{ formatCurrency(stats.p75!) }}
            </span>
          </div>
        </div>
        <p class="salary-calculator__sub">
          {{ salaryCountLine(stats) }}
        </p>
      </template>
      <p v-else class="salary-calculator__empty">
        {{ SALARY_EMPTY_STATE_TEXT }}
      </p>
    </template>
  </div>
</template>

<style scoped>
.salary-calculator {
  padding: var(--space-4) var(--space-6) var(--space-12);
  max-width: 720px;
  margin: 0 auto;
}

.salary-calculator__title {
  font-family: var(--font-display);
  font-size: var(--text-2xl);
  color: var(--color-text);
  margin: 0 0 var(--space-3);
}

.salary-calculator__framing {
  color: var(--color-text-muted);
  font-size: var(--text-sm);
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  margin: 0 0 var(--space-6);
}

.salary-calculator__form {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  align-items: flex-end;
  margin-bottom: var(--space-6);
}

.salary-calculator__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  flex: 1 1 200px;
  min-width: 0;
}

.salary-calculator__field label {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-weight: 600;
}

.salary-calculator__field input {
  font: inherit;
  font-size: var(--text-sm);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  color: var(--color-text);
  width: 100%;
  box-sizing: border-box;
}

.salary-calculator__recalculate {
  font: inherit;
  font-size: var(--text-sm);
  font-weight: 600;
  padding: var(--space-2) var(--space-4);
  border: none;
  border-radius: var(--radius-md);
  background: var(--app-primary, var(--color-primary));
  color: var(--color-text-inverse);
  cursor: pointer;
  white-space: nowrap;
}

.salary-calculator__recalculate:disabled {
  opacity: 0.6;
  cursor: default;
}

.salary-calculator__recalculate:hover:not(:disabled) {
  background: var(--app-primary-hover, var(--color-primary-hover));
}

.salary-calculator__loading,
.salary-calculator__error {
  color: var(--color-text-muted);
  font-size: var(--text-sm);
}

.salary-calculator__error {
  color: var(--color-error);
}

.salary-calculator__count {
  color: var(--color-text);
  font-size: var(--text-sm);
  margin-bottom: var(--space-3);
}

.salary-calculator__bar-wrap {
  margin-bottom: var(--space-2);
}

.salary-calculator__bar {
  position: relative;
  height: var(--space-4);
  border-radius: var(--radius-full);
  background: linear-gradient(
    to right,
    var(--color-primary-light),
    var(--color-primary),
    var(--color-primary-light)
  );
}

.salary-calculator__bar-marker {
  position: absolute;
  top: -4px;
  bottom: -4px;
  width: 3px;
  background: var(--color-accent);
  transform: translateX(-50%);
  border-radius: var(--radius-full);
}

.salary-calculator__bar-labels {
  display: flex;
  justify-content: space-between;
  gap: var(--space-2);
  margin-top: var(--space-2);
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  flex-wrap: wrap;
}

.salary-calculator__bar-label--median {
  font-weight: 700;
  color: var(--color-accent);
  text-align: center;
  flex: 1 1 auto;
}

.salary-calculator__sub,
.salary-calculator__empty {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

@media (max-width: 400px) {
  .salary-calculator {
    padding: var(--space-3) var(--space-3) var(--space-8);
  }

  .salary-calculator__form {
    flex-direction: column;
    align-items: stretch;
  }

  .salary-calculator__recalculate {
    width: 100%;
  }
}
</style>
