<template>
  <div class="rv">
    <div class="rv__header">
      <h1 class="rv__title">Resume Library</h1>
      <label class="btn-generate rv__import-btn">
        <span aria-hidden="true">📥</span> Import
        <input type="file" accept=".txt,.pdf,.docx,.odt,.yaml,.yml"
          class="rv__file-input" @change="handleImport" />
      </label>
    </div>

    <div v-if="loading" class="rv__loading">Loading…</div>

    <div v-else-if="resumes.length === 0" class="rv__empty">
      <p>No resumes saved yet.</p>
      <p>Import a resume file or save an optimized resume from the Apply workspace.</p>
    </div>

    <div v-else class="rv__layout">
      <!-- Left: list -->
      <ul class="rv__list" role="listbox" aria-label="Saved resumes">
        <li
          v-for="r in resumes"
          :key="r.id"
          role="option"
          :aria-selected="selected?.id === r.id"
          class="rv__list-item"
          :class="{ 'rv__list-item--active': selected?.id === r.id }"
          @click="select(r)"
        >
          <span class="rv__item-star" :aria-label="r.is_default ? 'Default resume' : ''">
            {{ r.is_default ? '★' : '☆' }}
          </span>
          <div class="rv__item-info">
            <span class="rv__item-name">{{ r.name }}</span>
            <span class="rv__item-meta">{{ r.word_count }} words · {{ fmtDate(r.created_at) }}</span>
            <span v-if="r.job_id" class="rv__item-source">Built for job #{{ r.job_id }}</span>
          </div>
        </li>
      </ul>

      <!-- Right: preview + actions -->
      <div v-if="selected" class="rv__preview-pane">
        <div class="rv__preview-header">
          <div class="rv__preview-meta">
            <h2 class="rv__preview-name">{{ editing ? editName : selected.name }}</h2>
            <span class="rv__preview-words">{{ selected.word_count }} words</span>
            <span v-if="selected.is_default" class="rv__default-badge">Default</span>
          </div>
          <div class="rv__preview-actions">
            <button v-if="!selected.is_default" class="btn-secondary" @click="setDefault">
              ★ Set as Default
            </button>
            <button class="btn-secondary" @click="toggleEdit">
              {{ editing ? 'Cancel' : 'Edit' }}
            </button>
            <div class="rv__download-menu">
              <button class="btn-secondary" @click="showDownloadMenu = !showDownloadMenu">
                Download ▾
              </button>
              <ul v-if="showDownloadMenu" class="rv__download-dropdown">
                <li><button @click="downloadTxt">Download .txt</button></li>
                <li><button @click="downloadPdf">Download PDF</button></li>
                <li><button @click="downloadYaml">Download YAML</button></li>
              </ul>
            </div>
            <button class="rv__delete-btn" @click="confirmDelete"
              :disabled="resumes.length === 1 || selected.is_default === 1">
              Delete
            </button>
          </div>
        </div>

        <!-- Edit name inline -->
        <input v-if="editing" v-model="editName" class="rv__edit-name-input" maxlength="80" placeholder="Resume name" />

        <!-- Text editor / preview -->
        <textarea
          v-model="editText"
          class="rv__textarea"
          :readonly="!editing"
          spellcheck="false"
          aria-label="Resume text"
        />

        <div v-if="editing" class="rv__edit-actions">
          <button class="btn-generate" :disabled="saving" @click="saveEdit">
            {{ saving ? 'Saving…' : 'Save' }}
          </button>
          <button class="btn-secondary" @click="toggleEdit">Discard</button>
        </div>

        <p v-if="actionError" class="rv__error" role="alert">{{ actionError }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useApiFetch } from '../composables/useApi'

interface Resume {
  id: number; name: string; source: string; job_id: number | null
  text: string; struct_json: string | null; word_count: number
  is_default: number; created_at: string; updated_at: string
}

const resumes      = ref<Resume[]>([])
const selected     = ref<Resume | null>(null)
const loading      = ref(true)
const editing      = ref(false)
const editName     = ref('')
const editText     = ref('')
const saving       = ref(false)
const actionError  = ref('')
const showDownloadMenu = ref(false)

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

async function loadList() {
  loading.value = true
  const { data } = await useApiFetch<{ resumes: Resume[] }>('/api/resumes')
  resumes.value = data?.resumes ?? []
  if (resumes.value.length && !selected.value) select(resumes.value[0])
  loading.value = false
}

function select(r: Resume) {
  selected.value = r
  editing.value = false
  editName.value = r.name
  editText.value = r.text
  actionError.value = ''
  showDownloadMenu.value = false
}

function toggleEdit() {
  if (editing.value) {
    editing.value = false
    editName.value = selected.value?.name ?? ''
    editText.value = selected.value?.text ?? ''
  } else {
    editing.value = true
  }
}

async function saveEdit() {
  if (!selected.value) return
  saving.value = true; actionError.value = ''
  const { data, error } = await useApiFetch<Resume>(
    `/api/resumes/${selected.value.id}`,
    { method: 'PATCH', body: JSON.stringify({ name: editName.value, text: editText.value }),
      headers: { 'Content-Type': 'application/json' } }
  )
  saving.value = false
  if (error || !data) { actionError.value = 'Save failed.'; return }
  const idx = resumes.value.findIndex(r => r.id === data.id)
  if (idx >= 0) resumes.value[idx] = data
  selected.value = data
  editing.value = false
}

async function setDefault() {
  if (!selected.value) return
  actionError.value = ''
  const { error } = await useApiFetch(`/api/resumes/${selected.value.id}/set-default`, { method: 'POST' })
  if (error) { actionError.value = 'Failed to set default.'; return }
  await loadList()
  if (selected.value) {
    const refreshed = resumes.value.find(r => r.id === selected.value!.id)
    if (refreshed) select(refreshed)
  }
}

async function confirmDelete() {
  if (!selected.value) return
  if (!window.confirm(`Delete "${selected.value.name}"? This cannot be undone.`)) return
  actionError.value = ''
  const { error } = await useApiFetch(`/api/resumes/${selected.value.id}`, { method: 'DELETE' })
  if (error) { actionError.value = 'Delete failed — check if this is the default resume.'; return }
  selected.value = null
  await loadList()
}

async function handleImport(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  actionError.value = ''
  const form = new FormData()
  form.append('file', file)
  const { data, error } = await useApiFetch<Resume>('/api/resumes/import', { method: 'POST', body: form })
  if (error || !data) { actionError.value = 'Import failed — check file format.'; return }
  resumes.value = [data, ...resumes.value]
  select(data)
}

function downloadTxt() {
  if (!selected.value) return
  const blob = new Blob([selected.value.text], { type: 'text/plain' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `${selected.value.name.replace(/\s+/g, '-')}.txt`
  a.click()
  URL.revokeObjectURL(a.href)
  showDownloadMenu.value = false
}

function downloadPdf() {
  if (!selected.value) return
  window.open(`/api/resumes/${selected.value.id}/export-pdf`, '_blank')
  showDownloadMenu.value = false
}

function downloadYaml() {
  if (!selected.value) return
  window.open(`/api/resumes/${selected.value.id}/export-yaml`, '_blank')
  showDownloadMenu.value = false
}

onMounted(loadList)
</script>

<style scoped>
.rv { display: flex; flex-direction: column; gap: var(--space-4, 1rem); padding: var(--space-5, 1.25rem); height: 100%; }

.rv__header { display: flex; align-items: center; justify-content: space-between; }
.rv__title { font-size: var(--font-xl, 1.25rem); font-weight: 700; margin: 0; }
.rv__file-input { display: none; }
.rv__import-btn { cursor: pointer; }

.rv__layout { display: grid; grid-template-columns: 260px 1fr; gap: var(--space-4, 1rem); flex: 1; min-height: 0; }

.rv__list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-1, 0.25rem); overflow-y: auto; }
.rv__list-item {
  display: flex; align-items: flex-start; gap: var(--space-2, 0.5rem);
  padding: var(--space-3, 0.75rem); border-radius: var(--radius-md, 0.5rem);
  cursor: pointer; border: 1px solid transparent;
}
.rv__list-item:hover { background: var(--color-surface-alt, #f8fafc); }
.rv__list-item--active { background: var(--color-surface-alt, #f8fafc); border-color: var(--color-accent, #6366f1); }

.rv__item-star { color: var(--color-warning, #f59e0b); font-size: 1rem; flex-shrink: 0; margin-top: 2px; }
.rv__item-info { display: flex; flex-direction: column; gap: 2px; }
.rv__item-name { font-weight: 500; font-size: var(--font-sm, 0.875rem); }
.rv__item-meta { font-size: var(--font-xs, 0.75rem); color: var(--color-text-muted, #64748b); }
.rv__item-source { font-size: var(--font-xs, 0.75rem); color: var(--color-accent, #6366f1); }

.rv__preview-pane { display: flex; flex-direction: column; gap: var(--space-3, 0.75rem); min-height: 0; }
.rv__preview-header { display: flex; align-items: flex-start; justify-content: space-between; flex-wrap: wrap; gap: var(--space-3, 0.75rem); }
.rv__preview-meta { display: flex; align-items: center; gap: var(--space-2, 0.5rem); flex-wrap: wrap; }
.rv__preview-name { font-size: var(--font-lg, 1.125rem); font-weight: 600; margin: 0; }
.rv__preview-words { font-size: var(--font-sm, 0.875rem); color: var(--color-text-muted, #64748b); }
.rv__default-badge {
  font-size: var(--font-xs, 0.75rem); font-weight: 600;
  background: var(--color-success, #16a34a); color: #fff;
  padding: 2px 8px; border-radius: 9999px;
}
.rv__preview-actions { display: flex; gap: var(--space-2, 0.5rem); flex-wrap: wrap; align-items: center; }
.rv__delete-btn {
  color: var(--color-error, #dc2626); background: none;
  border: 1px solid var(--color-error, #dc2626);
  border-radius: var(--radius-md, 0.5rem);
  padding: var(--space-2, 0.5rem) var(--space-3, 0.75rem);
  cursor: pointer; font-size: var(--font-sm, 0.875rem);
}
.rv__delete-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.rv__edit-name-input {
  width: 100%; padding: var(--space-2, 0.5rem) var(--space-3, 0.75rem);
  border: 1px solid var(--color-border, #e2e8f0); border-radius: var(--radius-md, 0.5rem);
  font-size: var(--font-base, 1rem);
}
.rv__textarea {
  flex: 1; min-height: 400px; padding: var(--space-3, 0.75rem);
  border: 1px solid var(--color-border, #e2e8f0); border-radius: var(--radius-md, 0.5rem);
  font-family: monospace; font-size: var(--font-sm, 0.875rem); resize: vertical;
  background: var(--color-surface-alt, #f8fafc);
}
.rv__textarea:not([readonly]) { background: var(--color-surface, #fff); }
.rv__edit-actions { display: flex; gap: var(--space-2, 0.5rem); }
.rv__error { color: var(--color-error, #dc2626); font-size: var(--font-sm, 0.875rem); }

.rv__download-menu { position: relative; }
.rv__download-dropdown {
  position: absolute; top: 100%; right: 0; z-index: 10;
  background: var(--color-surface, #fff); border: 1px solid var(--color-border, #e2e8f0);
  border-radius: var(--radius-md, 0.5rem); list-style: none; margin: 4px 0; padding: var(--space-1, 0.25rem);
  min-width: 140px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);
}
.rv__download-dropdown button {
  width: 100%; text-align: left; background: none; border: none;
  padding: var(--space-2, 0.5rem) var(--space-3, 0.75rem);
  cursor: pointer; font-size: var(--font-sm, 0.875rem); border-radius: var(--radius-sm, 0.25rem);
}
.rv__download-dropdown button:hover { background: var(--color-surface-alt, #f8fafc); }

.rv__loading, .rv__empty { color: var(--color-text-muted, #64748b); font-size: var(--font-sm, 0.875rem); }

@media (max-width: 640px) {
  .rv__layout { grid-template-columns: 1fr; }
  .rv__list { max-height: 200px; }
}
</style>
