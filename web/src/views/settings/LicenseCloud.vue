<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useAppConfigStore } from '../../stores/appConfig'

const { tier } = storeToRefs(useAppConfigStore())
</script>

<template>
  <div class="form-section">
    <h2>Plan</h2>
    <div class="license-info">
      <span class="tier-badge">{{ tier?.toUpperCase() ?? 'FREE' }}</span>
    </div>
    <p class="section-note">
      Manage your subscription at <a href="https://circuitforge.tech/account" target="_blank">circuitforge.tech/account</a>
    </p>
  </div>
</template>
