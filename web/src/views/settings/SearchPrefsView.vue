<template>
  <div class="search-prefs">
    <div class="page-header">
      <h2>Search Preferences</h2>
      <a :href="docsUrl" target="_blank" rel="noopener" class="help-link" aria-label="Search Preferences documentation">? Help</a>
    </div>
    <p v-if="store.loadError" class="error-banner">{{ store.loadError }}</p>

    <!-- Remote Preference -->
    <section class="form-section">
      <h3>Remote Preference</h3>
      <div class="remote-options">
        <button
          v-for="opt in remoteOptions"
          :key="opt.value"
          :class="['remote-btn', { active: store.remote_preference === opt.value }]"
          @click="store.remote_preference = opt.value"
        >{{ opt.label }}</button>
      </div>
      <p class="section-note">This filter runs at scrape time — listings that don't match are excluded before they count against per-board quotas.</p>
    </section>

    <!-- Job Titles -->
    <section class="form-section">
      <h3>Job Titles</h3>
      <div class="tags">
        <span v-for="title in store.job_titles" :key="title" class="tag">
          {{ title }} <button @click="store.removeTag('job_titles', title)">×</button>
        </span>
      </div>
      <div class="tag-input-row">
        <input v-model="titleInput" @keydown.enter.prevent="addTitle" placeholder="Add title, press Enter" />
        <button @click="store.suggestTitles()" class="btn-suggest">Suggest</button>
      </div>
      <div v-if="store.titleSuggestions.length > 0" class="suggestions">
        <span
          v-for="s in store.titleSuggestions"
          :key="s"
          class="suggestion-chip"
          @click="store.acceptSuggestion('title', s)"
        >+ {{ s }}</span>
      </div>
    </section>

    <!-- Locations -->
    <section class="form-section">
      <h3>Locations</h3>
      <div class="tags">
        <span v-for="loc in store.locations" :key="loc" class="tag">
          {{ loc }} <button @click="store.removeTag('locations', loc)">×</button>
        </span>
      </div>
      <div class="tag-input-row">
        <input v-model="locationInput" @keydown.enter.prevent="addLocation" placeholder="Add location, press Enter" />
        <button @click="store.suggestLocations()" class="btn-suggest">Suggest</button>
      </div>
      <div v-if="store.locationSuggestions.length > 0" class="suggestions">
        <span
          v-for="s in store.locationSuggestions"
          :key="s"
          class="suggestion-chip"
          @click="store.acceptSuggestion('location', s)"
        >+ {{ s }}</span>
      </div>
    </section>

    <!-- Exclude Keywords -->
    <section class="form-section">
      <h3>Exclude Keywords</h3>
      <div class="tags">
        <span v-for="kw in store.exclude_keywords" :key="kw" class="tag">
          {{ kw }} <button @click="store.removeTag('exclude_keywords', kw)">×</button>
        </span>
      </div>
      <div class="tag-input-row">
        <input v-model="excludeInput" @keydown.enter.prevent="store.addTag('exclude_keywords', excludeInput); excludeInput = ''" placeholder="Add keyword, press Enter" />
        <button @click="store.suggestExcludeKeywords()" class="btn-suggest">Suggest</button>
      </div>
      <div v-if="store.excludeSuggestions.length > 0" class="suggestions">
        <span
          v-for="s in store.excludeSuggestions"
          :key="s"
          class="suggestion-chip"
          @click="store.acceptSuggestion('exclude', s)"
        >+ {{ s }}</span>
      </div>
    </section>

    <!-- Job Boards -->
    <section class="form-section">
      <h3>Job Boards</h3>
      <div v-for="board in store.job_boards" :key="board.name" class="board-row" :class="{ 'board-row--unsupported': board.supported === false }">
        <label class="checkbox-row">
          <input
            type="checkbox"
            :checked="board.enabled"
            :disabled="board.supported === false"
            @change="store.toggleBoard(board.name)"
          />
          {{ board.name }}
          <span v-if="board.supported === false" class="board-badge board-badge--pending" title="Not yet implemented — tracked in backlog">coming soon</span>
        </label>
      </div>
      <div class="field-row" style="margin-top: 12px">
        <label>Custom Board URLs</label>
        <div class="tags">
          <span v-for="url in store.custom_board_urls" :key="url" class="tag">
            {{ url }} <button @click="store.removeTag('custom_board_urls', url)">×</button>
          </span>
        </div>
        <input v-model="customUrlInput" @keydown.enter.prevent="store.addTag('custom_board_urls', customUrlInput); customUrlInput = ''" placeholder="https://..." />
      </div>
    </section>

    <!-- Blocklists -->
    <section class="form-section">
      <h3>Blocklists</h3>
      <div class="blocklist-group">
        <label>Companies</label>
        <div class="tags">
          <span v-for="c in store.blocklist_companies" :key="c" class="tag">
            {{ c }} <button @click="store.removeTag('blocklist_companies', c)">×</button>
          </span>
        </div>
        <input v-model="blockCompanyInput" @keydown.enter.prevent="store.addTag('blocklist_companies', blockCompanyInput); blockCompanyInput = ''" placeholder="Company name" />
      </div>
      <div class="blocklist-group">
        <label>Industries</label>
        <div class="tags">
          <span v-for="i in store.blocklist_industries" :key="i" class="tag">
            {{ i }} <button @click="store.removeTag('blocklist_industries', i)">×</button>
          </span>
        </div>
        <input v-model="blockIndustryInput" @keydown.enter.prevent="store.addTag('blocklist_industries', blockIndustryInput); blockIndustryInput = ''" placeholder="Industry name" />
      </div>
      <div class="blocklist-group">
        <label>Locations</label>
        <div class="tags">
          <span v-for="l in store.blocklist_locations" :key="l" class="tag">
            {{ l }} <button @click="store.removeTag('blocklist_locations', l)">×</button>
          </span>
        </div>
        <input v-model="blockLocationInput" @keydown.enter.prevent="store.addTag('blocklist_locations', blockLocationInput); blockLocationInput = ''" placeholder="Location name" />
      </div>
    </section>

    <!-- Save -->
    <div class="form-actions">
      <button @click="store.save()" :disabled="store.saving" class="btn-primary">
        {{ store.saving ? 'Saving…' : 'Save Search Preferences' }}
      </button>
      <p v-if="store.saveError" class="error">{{ store.saveError }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useSearchStore } from '../../stores/settings/search'
import { useDocsUrl } from '../../composables/useDocsUrl'

const store = useSearchStore()
const docsUrl = useDocsUrl('user-guide/settings/#search-prefs')

const remoteOptions = [
  { value: 'remote' as const, label: 'Remote only' },
  { value: 'onsite' as const, label: 'On-site only' },
  { value: 'both' as const, label: 'Both' },
]

const titleInput = ref('')
const locationInput = ref('')
const excludeInput = ref('')
const customUrlInput = ref('')
const blockCompanyInput = ref('')
const blockIndustryInput = ref('')
const blockLocationInput = ref('')

function addTitle() {
  store.addTag('job_titles', titleInput.value)
  titleInput.value = ''
}

function addLocation() {
  store.addTag('locations', locationInput.value)
  locationInput.value = ''
}

onMounted(() => store.load())
</script>

<style scoped>
.search-prefs { max-width: 720px; margin: 0 auto; padding: var(--space-4); }
.page-header { display: flex; align-items: center; gap: var(--space-3); margin-bottom: var(--space-6); }
.page-header h2 { margin-bottom: 0; }
.help-link { font-size: 0.75rem; color: var(--color-text-muted); border: 1px solid var(--color-border); border-radius: var(--radius-full); padding: 2px 8px; text-decoration: none; white-space: nowrap; flex-shrink: 0; }
.help-link:hover { color: var(--color-primary); border-color: var(--color-primary); }
h2 { font-size: 1.4rem; font-weight: 600; margin-bottom: var(--space-6); }
h3 { font-size: 1rem; font-weight: 600; margin-bottom: var(--space-3); }
.form-section { margin-bottom: var(--space-8); padding-bottom: var(--space-6); border-bottom: 1px solid var(--color-border); }
.remote-options { display: flex; gap: 8px; margin-bottom: 10px; }
.remote-btn { padding: 8px 18px; border-radius: 6px; border: 1px solid var(--color-border); background: transparent; color: var(--color-text-muted); cursor: pointer; font-size: 0.88rem; transition: all 0.15s; }
.remote-btn.active { background: var(--color-accent); border-color: var(--color-accent); color: var(--color-text-inverse); }
.section-note { font-size: 0.78rem; color: var(--color-text-muted); margin-top: 8px; }
.tags { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.tag {
  padding: 3px 10px;
  background: color-mix(in srgb, var(--color-accent) 15%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-accent) 30%, transparent);
  border-radius: 12px; font-size: 0.78rem; color: var(--color-accent);
  display: flex; align-items: center; gap: 5px;
}
.tag button { background: none; border: none; color: inherit; cursor: pointer; padding: 0; line-height: 1; }
.tag-input-row { display: flex; gap: 8px; }
.tag-input-row input, input[type="text"], input:not([type]) {
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
  border-radius: 6px; color: var(--color-text);
  padding: 7px 10px; font-size: 0.85rem; flex: 1; box-sizing: border-box;
}
.btn-suggest {
  padding: 7px 14px; border-radius: 6px;
  background: color-mix(in srgb, var(--color-accent) 20%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-accent) 30%, transparent);
  color: var(--color-accent); cursor: pointer; font-size: 0.82rem; white-space: nowrap;
}
.suggestions { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.suggestion-chip {
  padding: 4px 12px; border-radius: 12px; font-size: 0.78rem;
  background: var(--color-surface-alt);
  border: 1px dashed var(--color-border);
  color: var(--color-text-muted); cursor: pointer; transition: all 0.15s;
}
.suggestion-chip:hover {
  background: color-mix(in srgb, var(--color-accent) 15%, transparent);
  border-color: color-mix(in srgb, var(--color-accent) 30%, transparent);
  color: var(--color-accent);
}
.board-row { margin-bottom: 8px; }
.board-row--unsupported { opacity: 0.5; }
.board-row--unsupported input[type="checkbox"] { cursor: not-allowed; }

.board-badge {
  display: inline-block;
  margin-left: var(--space-2);
  padding: 1px 6px;
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: 600;
  vertical-align: middle;
}
.board-badge--pending {
  background: var(--color-surface-alt);
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
}
.checkbox-row { display: flex; align-items: center; gap: 8px; font-size: 0.88rem; color: var(--color-text); cursor: pointer; }
.field-row { display: flex; flex-direction: column; gap: 6px; }
.field-row label { font-size: 0.82rem; color: var(--color-text-muted); }
.blocklist-group { margin-bottom: var(--space-4); }
.blocklist-group label { font-size: 0.82rem; color: var(--color-text-muted); display: block; margin-bottom: 6px; }
.form-actions { margin-top: var(--space-6); display: flex; align-items: center; gap: var(--space-4); }
.btn-primary { padding: 9px 24px; background: var(--color-accent); color: var(--color-text-inverse); border: none; border-radius: 7px; font-size: 0.9rem; cursor: pointer; font-weight: 600; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.error-banner {
  background: color-mix(in srgb, var(--color-error) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-error) 30%, transparent);
  border-radius: 6px; color: var(--color-error); padding: 10px 14px; margin-bottom: 20px; font-size: 0.85rem;
}
.error { color: var(--color-error); font-size: 0.82rem; }
</style>
