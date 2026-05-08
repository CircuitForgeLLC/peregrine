<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useApiFetch } from '../composables/useApi'

export interface Reference {
  id:           number
  name:         string
  relationship: string
  company:      string
  email:        string
  phone:        string
  notes:        string
  tags:         string   // JSON-encoded string[]
  created_at:   string
  updated_at:   string
}

const TAG_OPTIONS = ['technical', 'managerial', 'character', 'academic'] as const

const references  = ref<Reference[]>([])
const loading     = ref(false)
const saving      = ref(false)
const editingId   = ref<number | 'new' | null>(null)
const deleteConfirmId = ref<number | null>(null)

const blankForm = () => ({
  name: '', relationship: '', company: '', email: '', phone: '', notes: '', tags: [] as string[],
})
const form = ref(blankForm())

async function fetchRefs() {
  loading.value = true
  const { data } = await useApiFetch<Reference[]>('/api/references')
  loading.value = false
  if (data) references.value = data
}

function parseTags(raw: string): string[] {
  try { return JSON.parse(raw) } catch { return [] }
}

function startNew() {
  form.value = blankForm()
  editingId.value = 'new'
}

function startEdit(ref: Reference) {
  form.value = {
    name: ref.name,
    relationship: ref.relationship,
    company: ref.company,
    email: ref.email,
    phone: ref.phone,
    notes: ref.notes,
    tags: parseTags(ref.tags),
  }
  editingId.value = ref.id
}

function cancelEdit() {
  editingId.value = null
  form.value = blankForm()
}

async function saveRef() {
  if (!form.value.name.trim()) return
  saving.value = true
  const isNew = editingId.value === 'new'
  const url = isNew ? '/api/references' : `/api/references/${editingId.value}`
  const { data, error } = await useApiFetch<Reference>(url, {
    method: isNew ? 'POST' : 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(form.value),
  })
  saving.value = false
  if (error || !data) return
  if (isNew) {
    references.value = [...references.value, data]
  } else {
    references.value = references.value.map(r => r.id === data.id ? data : r)
  }
  cancelEdit()
}

async function deleteRef(id: number) {
  await useApiFetch(`/api/references/${id}`, { method: 'DELETE' })
  references.value = references.value.filter(r => r.id !== id)
  deleteConfirmId.value = null
}

function tagLabel(tag: string): string {
  const map: Record<string, string> = {
    technical: 'Technical', managerial: 'Manager', character: 'Character', academic: 'Academic',
  }
  return map[tag] ?? tag
}

onMounted(fetchRefs)
</script>

<template>
  <div class="refs-view">
    <header class="refs-header">
      <div class="refs-header__left">
        <h1 class="refs-title">References</h1>
        <span v-if="references.length" class="refs-count">{{ references.length }}</span>
      </div>
      <button class="btn-add" @click="startNew" :disabled="editingId !== null">
        + Add reference
      </button>
    </header>

    <p class="refs-hint">
      Store your references once, associate them with applications, and generate
      a heads-up email or draft recommendation letter with one click.
    </p>

    <!-- New / edit form -->
    <div v-if="editingId !== null" class="ref-form">
      <h2 class="ref-form__title">{{ editingId === 'new' ? 'Add reference' : 'Edit reference' }}</h2>
      <div class="ref-form__grid">
        <label class="ref-form__field ref-form__field--full">
          <span>Name <span class="required">*</span></span>
          <input v-model="form.name" class="ref-input" placeholder="Full name" />
        </label>
        <label class="ref-form__field">
          <span>Relationship</span>
          <input v-model="form.relationship" class="ref-input" placeholder="e.g. Former manager" />
        </label>
        <label class="ref-form__field">
          <span>Company</span>
          <input v-model="form.company" class="ref-input" placeholder="Where you worked together" />
        </label>
        <label class="ref-form__field">
          <span>Email</span>
          <input v-model="form.email" class="ref-input" type="email" placeholder="email@example.com" />
        </label>
        <label class="ref-form__field">
          <span>Phone</span>
          <input v-model="form.phone" class="ref-input" type="tel" placeholder="+1 555 000 0000" />
        </label>
        <label class="ref-form__field ref-form__field--full">
          <span>Notes</span>
          <textarea v-model="form.notes" class="ref-input ref-textarea"
            placeholder="Accomplishments they can speak to, context, anything to remind yourself…"
            rows="2" />
        </label>
        <div class="ref-form__field ref-form__field--full">
          <span>Type</span>
          <div class="ref-tags">
            <label v-for="t in TAG_OPTIONS" :key="t" class="ref-tag-option">
              <input type="checkbox" :value="t" v-model="form.tags" />
              {{ tagLabel(t) }}
            </label>
          </div>
        </div>
      </div>
      <div class="ref-form__actions">
        <button class="btn-save" @click="saveRef" :disabled="saving || !form.name.trim()">
          {{ saving ? 'Saving…' : editingId === 'new' ? 'Add' : 'Save' }}
        </button>
        <button class="btn-cancel" @click="cancelEdit">Cancel</button>
      </div>
    </div>

    <!-- Empty state -->
    <div v-if="!loading && references.length === 0 && editingId === null" class="refs-empty">
      No references yet. Add someone who can speak to your work.
    </div>

    <!-- Reference cards -->
    <ul v-else class="refs-list" aria-label="References">
      <li
        v-for="ref in references"
        :key="ref.id"
        class="ref-card"
        :class="{ 'ref-card--editing': editingId === ref.id }"
      >
        <div class="ref-card__body">
          <div class="ref-card__name">{{ ref.name }}</div>
          <div class="ref-card__meta">
            <span v-if="ref.relationship">{{ ref.relationship }}</span>
            <span v-if="ref.relationship && ref.company" class="sep"> · </span>
            <span v-if="ref.company">{{ ref.company }}</span>
          </div>
          <div class="ref-card__contact">
            <a v-if="ref.email" :href="`mailto:${ref.email}`" class="ref-link">{{ ref.email }}</a>
            <span v-if="ref.email && ref.phone" class="sep"> · </span>
            <span v-if="ref.phone">{{ ref.phone }}</span>
          </div>
          <div v-if="ref.notes" class="ref-card__notes">{{ ref.notes }}</div>
          <div v-if="parseTags(ref.tags).length" class="ref-card__tags">
            <span v-for="t in parseTags(ref.tags)" :key="t" class="tag-chip" :class="`tag-chip--${t}`">
              {{ tagLabel(t) }}
            </span>
          </div>
        </div>
        <div class="ref-card__actions">
          <button class="btn-ghost" @click="startEdit(ref)" :disabled="editingId !== null">Edit</button>
          <button
            v-if="deleteConfirmId !== ref.id"
            class="btn-ghost btn-ghost--danger"
            @click="deleteConfirmId = ref.id"
            :disabled="editingId !== null"
          >Delete</button>
          <template v-else>
            <button class="btn-ghost btn-ghost--danger" @click="deleteRef(ref.id)">Confirm</button>
            <button class="btn-ghost" @click="deleteConfirmId = null">Cancel</button>
          </template>
        </div>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.refs-view {
  padding: var(--space-6);
  max-width: 760px;
}

.refs-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-2);
}

.refs-header__left {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
}

.refs-title {
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--color-text);
  margin: 0;
}

.refs-count {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

.refs-hint {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  margin: 0 0 var(--space-5);
  line-height: 1.5;
}

.btn-add {
  padding: var(--space-2) var(--space-4);
  background: var(--app-primary);
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: pointer;
}

.btn-add:disabled { opacity: 0.5; cursor: not-allowed; }

/* Form */
.ref-form {
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border);
  border-radius: 10px;
  padding: var(--space-5);
  margin-bottom: var(--space-5);
}

.ref-form__title {
  font-size: var(--text-lg);
  font-weight: 600;
  margin: 0 0 var(--space-4);
}

.ref-form__grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3);
}

.ref-form__field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

.ref-form__field--full { grid-column: 1 / -1; }

.required { color: var(--color-error, #c0392b); }

.ref-input {
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-surface);
  color: var(--color-text);
  font-size: var(--text-sm);
}

.ref-input:focus-visible {
  outline: 2px solid var(--app-primary);
  outline-offset: 2px;
}

.ref-textarea { resize: vertical; font-family: inherit; }

.ref-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin-top: 4px;
}

.ref-tag-option {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: var(--text-sm);
  cursor: pointer;
}

.ref-form__actions {
  display: flex;
  gap: var(--space-2);
  margin-top: var(--space-4);
}

.btn-save {
  padding: var(--space-2) var(--space-4);
  background: var(--app-primary);
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: pointer;
}

.btn-save:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-cancel {
  padding: var(--space-2) var(--space-4);
  background: none;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  font-size: var(--text-sm);
  cursor: pointer;
  color: var(--color-text-muted);
}

/* Empty */
.refs-empty {
  color: var(--color-text-muted);
  font-size: var(--text-sm);
  padding: var(--space-8) 0;
  text-align: center;
}

/* List */
.refs-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.ref-card {
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border);
  border-radius: 10px;
  padding: var(--space-4);
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-4);
}

.ref-card--editing {
  border-color: var(--app-primary);
  box-shadow: 0 0 0 2px var(--app-primary-light);
}

.ref-card__body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.ref-card__name {
  font-weight: 600;
  font-size: var(--text-base);
  color: var(--color-text);
}

.ref-card__meta, .ref-card__contact {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

.ref-card__notes {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  margin-top: 4px;
  font-style: italic;
}

.ref-link {
  color: var(--app-primary);
  text-decoration: none;
}

.ref-link:hover { text-decoration: underline; }

.sep { margin: 0 2px; }

.ref-card__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: var(--space-2);
}

.tag-chip {
  padding: 2px 8px;
  border-radius: 999px;
  font-size: var(--text-xs);
  font-weight: 600;
}

.tag-chip--technical  { background: var(--app-primary-light);     color: var(--app-primary); }
.tag-chip--managerial { background: rgba(39, 174, 96, 0.12);      color: var(--color-success); }
.tag-chip--character  { background: rgba(212, 137, 26, 0.12);     color: var(--score-mid); }
.tag-chip--academic   { background: color-mix(in srgb, var(--status-synced) 12%, var(--color-surface)); color: var(--status-synced); }

.ref-card__actions {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  flex-shrink: 0;
}

.btn-ghost {
  background: none;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  padding: 3px var(--space-3);
  font-size: var(--text-xs);
  cursor: pointer;
  color: var(--color-text-muted);
  white-space: nowrap;
}

.btn-ghost:hover { background: var(--color-hover); }
.btn-ghost:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-ghost--danger { color: var(--color-error, #c0392b); border-color: rgba(192, 57, 43, 0.3); }
.btn-ghost--danger:hover { background: rgba(192, 57, 43, 0.07); }
</style>
