<template>
  <ApplyWorkspace
    :job-id="jobId"
    @job-removed="router.push('/apply')"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ApplyWorkspace from '../components/ApplyWorkspace.vue'

const route  = useRoute()
const router = useRouter()
const jobId  = computed(() => Number(route.params.id))
</script>
