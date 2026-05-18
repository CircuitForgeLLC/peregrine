<template>
  <div class="rp-skills">
    <h3 class="rp__heading">Skills</h3>
    <p class="rp__hint">Check each skill you genuinely have. Uncheck skills you don't and choose how to frame the gap.</p>

    <div class="rp__skill-list" role="group" aria-label="Proposed new skills">
      <div v-for="skill in section.added" :key="skill" class="rp__skill-group">
        <label class="rp__skill-chip" :class="{ 'rp__skill-chip--approved': approvedSkills.has(skill) }">
          <input type="checkbox" :checked="approvedSkills.has(skill)" @change="emit('toggleSkill', skill)" />
          {{ skill }}
        </label>
        <div v-if="!approvedSkills.has(skill)" class="rp__framing">
          <span class="rp__framing-label">Frame this gap:</span>
          <label><input type="radio" :name="`framing-${skill}`" value="skip"
            :checked="(skillFramings.get(skill)?.mode ?? 'skip') === 'skip'"
            @change="emit('setFramingMode', skill, 'skip')" /> Skip entirely</label>
          <label><input type="radio" :name="`framing-${skill}`" value="adjacent"
            :checked="skillFramings.get(skill)?.mode === 'adjacent'"
            @change="emit('setFramingMode', skill, 'adjacent')" /> Adjacent experience</label>
          <label><input type="radio" :name="`framing-${skill}`" value="learning"
            :checked="skillFramings.get(skill)?.mode === 'learning'"
            @change="emit('setFramingMode', skill, 'learning')" /> Actively learning</label>
          <textarea v-if="skillFramings.get(skill)?.mode === 'adjacent'"
            class="rp__framing-context" rows="2"
            placeholder="Describe related background"
            :value="skillFramings.get(skill)?.context ?? ''"
            @input="emit('setFramingContext', skill, ($event.target as HTMLTextAreaElement).value)" />
          <textarea v-else-if="skillFramings.get(skill)?.mode === 'learning'"
            class="rp__framing-context" rows="2"
            placeholder="Describe learning context"
            :value="skillFramings.get(skill)?.context ?? ''"
            @input="emit('setFramingContext', skill, ($event.target as HTMLTextAreaElement).value)" />
        </div>
      </div>
    </div>
    <p v-if="section.removed.length" class="rp__removed">Skills being removed: {{ section.removed.join(', ') }}</p>
  </div>
</template>

<script setup lang="ts">
import type { SkillsDiff } from '../ResumeReviewModal.vue'

type GapFraming = { mode: 'skip' | 'adjacent' | 'learning'; context: string }

defineProps<{
  section: SkillsDiff
  approvedSkills: Set<string>
  skillFramings: Map<string, GapFraming>
}>()

const emit = defineEmits<{
  toggleSkill: [skill: string]
  setFramingMode: [skill: string, mode: 'skip' | 'adjacent' | 'learning']
  setFramingContext: [skill: string, context: string]
}>()
</script>

<style scoped>
.rp-skills { display: flex; flex-direction: column; gap: var(--space-4, 1rem); }
.rp__heading { font-size: var(--font-lg, 1.125rem); font-weight: 600; margin: 0; color: var(--color-text, #1a2338); }
.rp__hint { font-size: var(--text-sm); color: var(--color-text-muted, #4a5c7a); margin: 0; }
.rp__skill-list { display: flex; flex-direction: column; gap: var(--space-3, 0.75rem); }
.rp__skill-group { display: flex; flex-direction: column; gap: var(--space-2, 0.5rem); }
.rp__skill-chip {
  display: inline-flex; align-items: center; gap: var(--space-2, 0.5rem);
  padding: var(--space-2, 0.5rem) var(--space-3, 0.75rem);
  border: 1px solid var(--color-border, #a8b8d0);
  border-radius: var(--radius-md, 0.5rem);
  cursor: pointer; font-size: var(--text-sm);
  background: var(--color-surface-raised, #f5f7fc);
  transition: background var(--transition, 200ms ease);
}
.rp__skill-chip--approved { background: var(--color-primary-light, #e8f2e7); border-color: var(--color-primary, #2d5a27); }
.rp__framing { padding: var(--space-2, 0.5rem) var(--space-3, 0.75rem); display: flex; flex-direction: column; gap: var(--space-2, 0.5rem); background: var(--color-surface-alt, #dde4f0); border-radius: var(--radius-sm, 0.25rem); }
.rp__framing-label { font-size: var(--font-xs, 0.75rem); font-weight: 600; color: var(--color-text-muted, #4a5c7a); }
.rp__framing-context { border: 1px solid var(--color-border, #a8b8d0); border-radius: var(--radius-sm, 0.25rem); padding: var(--space-2, 0.5rem); font-size: var(--text-sm); resize: vertical; }
.rp__removed { font-size: var(--text-sm); color: var(--color-text-muted, #4a5c7a); font-style: italic; }
</style>
