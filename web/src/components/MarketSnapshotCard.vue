<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { useApiFetch } from '../composables/useApi'

interface SalaryStats {
  count: number
  count_with_salary: number
  median: number | null
  p25: number | null
  p75: number | null
}

const loading = ref(true)
const errored = ref(false)
const stats = ref<SalaryStats | null>(null)

function formatCurrency(value: number): string {
  return `$${value.toLocaleString('en-US')}`
}

onMounted(async () => {
  const { data, error } = await useApiFetch<SalaryStats>('/api/salary-stats')
  if (error || !data) {
    errored.value = true
  } else {
    stats.value = data
  }
  loading.value = false
})
</script>

<template>
  <section class="market-snapshot" aria-labelledby="market-snapshot-heading">
    <h2 id="market-snapshot-heading" class="market-snapshot__title">Market Snapshot</h2>

    <p v-if="loading" class="market-snapshot__loading">Loading your search results…</p>

    <p v-else-if="errored" class="market-snapshot__error">
      Couldn't load your salary snapshot right now.
    </p>

    <template v-else-if="stats">
      <p class="market-snapshot__count">
        {{ stats.count }} open {{ stats.count === 1 ? 'role' : 'roles' }} in your search results
      </p>

      <template v-if="stats.count_with_salary > 0">
        <p class="market-snapshot__range">
          Median {{ formatCurrency(stats.p25 ?? 0) }}–{{ formatCurrency(stats.p75 ?? 0) }}
        </p>
        <p class="market-snapshot__sub">
          based on {{ stats.count_with_salary }} of {{ stats.count }} roles with a listed salary
        </p>
      </template>
      <p v-else class="market-snapshot__sub">
        No salary data in your current search results yet
      </p>
    </template>

    <RouterLink to="/salary-calculator" class="market-snapshot__link">
      Full calculator →
    </RouterLink>
  </section>
</template>

<style scoped>
.market-snapshot {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-4);
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
}

.market-snapshot__title {
  font-family: var(--font-display);
  font-size: var(--text-lg);
  color: var(--color-text);
}

.market-snapshot__loading,
.market-snapshot__error {
  color: var(--color-text-muted);
  font-size: var(--text-sm);
}

.market-snapshot__count {
  color: var(--color-text);
  font-size: var(--text-sm);
}

.market-snapshot__range {
  font-family: var(--font-display);
  font-size: var(--text-xl);
  font-weight: 700;
  color: var(--color-primary);
}

.market-snapshot__sub {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.market-snapshot__link {
  align-self: flex-start;
  margin-top: var(--space-2);
  color: var(--color-accent);
  text-decoration: none;
  font-size: var(--text-sm);
  font-weight: 600;
}

.market-snapshot__link:hover {
  color: var(--color-accent-hover);
  text-decoration: underline;
}
</style>
