<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { useApiFetch } from '../composables/useApi'
import {
  formatCurrency,
  hasSalaryRange,
  salaryCountLine,
  salaryRolesLine,
  SALARY_EMPTY_STATE_TEXT,
  type SalaryStats,
} from '../composables/useSalaryStats'

const loading = ref(true)
const errored = ref(false)
const stats = ref<SalaryStats | null>(null)

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
        {{ salaryRolesLine(stats) }}
      </p>

      <template v-if="hasSalaryRange(stats)">
        <p class="market-snapshot__range">
          Typical range {{ formatCurrency(stats.p25!) }}–{{ formatCurrency(stats.p75!) }}
        </p>
        <p class="market-snapshot__sub">
          {{ salaryCountLine(stats) }}
        </p>
      </template>
      <p v-else class="market-snapshot__sub">
        {{ SALARY_EMPTY_STATE_TEXT }}
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
