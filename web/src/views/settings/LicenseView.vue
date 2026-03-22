<script setup lang="ts">
import { computed } from 'vue'
import { useAppConfigStore } from '../../stores/appConfig'
import LicenseSelfHosted from './LicenseSelfHosted.vue'
import LicenseCloud from './LicenseCloud.vue'

const config = useAppConfigStore()
const isCloud = computed(() => config.isCloud)
</script>

<template>
  <div class="license-view">
    <LicenseCloud v-if="isCloud" />
    <LicenseSelfHosted v-else />
  </div>
</template>
