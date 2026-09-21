// Shared type/formatter/copy for the salary-stats feature (MarketSnapshotCard
// and SalaryCalculatorView). Deliberately does NOT include fetch logic — the
// card fetches once on mount with no params, the view is store-gated and
// parameterized with a Recalculate button, and forcing those into one shared
// fetch composable would fit neither caller well.

export interface SalaryStats {
  count: number
  count_with_salary: number
  median: number | null
  p25: number | null
  p75: number | null
}

export function formatCurrency(value: number): string {
  return `$${value.toLocaleString('en-US')}`
}

/** "M of N roles with a listed salary" sub-line, shared verbatim by both surfaces. */
export function salaryCountLine(stats: SalaryStats): string {
  return `based on ${stats.count_with_salary} of ${stats.count} roles with a listed salary`
}

/** "N roles in your search results" count line — no status filter is applied
 * server-side, so this deliberately avoids "open" (rejected/applied/synced
 * listings are all included). */
export function salaryRolesLine(stats: SalaryStats): string {
  return `${stats.count} ${stats.count === 1 ? 'role' : 'roles'} in your search results`
}

export const SALARY_EMPTY_STATE_TEXT = 'No salary data in your current search results yet'

/** True only when the backend contract for a rendered salary range is fully
 * satisfied — guards against a contract violation rendering as "$0". */
export function hasSalaryRange(stats: SalaryStats): boolean {
  return stats.count_with_salary > 0 && stats.p25 != null && stats.p75 != null
}
