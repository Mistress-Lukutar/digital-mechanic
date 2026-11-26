<script setup lang="ts">
import type { AgentStepT } from '../types'
import { t } from '../i18n'

defineProps<{
  step: AgentStepT
}>()

function toolIcon(name: string): string {
  // Simple heuristic for icon character based on tool name
  if (name.includes('diagnostic') || name.includes('get_diagnostic')) return '🔍'
  if (name.includes('vehicle') || name.includes('info')) return '🚗'
  if (name.includes('document') || name.includes('rag') || name.includes('search')) return '📄'
  if (name.includes('ticket')) return '🎫'
  if (name.includes('check') || name.includes('signal')) return '📡'
  if (name.includes('analysis') || name.includes('analyze')) return '📊'
  return '⚙️'
}

function displayName(name: string): string {
  // Convert snake_case to readable Russian-ish label
  const map: Record<string, string> = {
    get_diagnostic_result: 'tools.get_diagnostic_result',
    get_vehicle_info: 'tools.get_vehicle_info',
    search_rag: 'tools.search_rag',
    create_ticket: 'tools.create_ticket',
    check_signal_quality: 'tools.check_signal_quality',
    analyze_signals: 'tools.analyze_signals',
  }
  const key = map[name] ?? null
  return key ? t(key as any) : name.replace(/_/g, ' ')
}
</script>

<template>
  <div :class="['agent-step', { error: step.is_error }]">
    <details v-if="step.done && step.content" class="step-details">
      <summary
        class="step-summary"
        :class="{ pending: !step.done, error: step.is_error }"
      >
        <span class="step-icon">{{ toolIcon(step.name) }}</span>
        <span class="step-name">{{ displayName(step.name) }}</span>

        <!-- Pending spinner -->
        <span v-if="!step.done" class="spinner" />

        <!-- Error indicator -->
        <span v-if="step.is_error" class="step-error-icon">!</span>

        <span v-if="step.summary" class="step-summary-text">{{ step.summary }}</span>
      </summary>

      <div class="step-content">
        <pre>{{ step.content }}</pre>
      </div>
    </details>

    <div v-else class="step-summary pending" :class="{ error: step.is_error }">
      <span class="step-icon">{{ toolIcon(step.name) }}</span>
      <span class="step-name">{{ displayName(step.name) }}</span>
      <span v-if="!step.done" class="spinner" />
      <span v-if="step.is_error" class="step-error-icon">!</span>
      <span v-if="step.summary && step.done" class="step-summary-text">{{ step.summary }}</span>
    </div>
  </div>
</template>

<style scoped>
.agent-step {
  margin: 4px 0;
}

.step-summary {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  font-size: 12px;
  cursor: default;
  color: var(--text-dim);
}

.step-summary.pending {
  cursor: default;
}

.step-summary:hover:not(.pending) {
  background: var(--bg-input);
}

.step-summary.error {
  color: var(--danger-text);
}

.step-icon {
  font-size: 13px;
  flex-shrink: 0;
}

.step-name {
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
}

.step-summary-text {
  color: var(--text-dim);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.step-error-icon {
  color: var(--danger);
  font-weight: 700;
  flex-shrink: 0;
}

.spinner {
  width: 12px;
  height: 12px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  flex-shrink: 0;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.step-content {
  margin-top: 4px;
  padding: 8px;
  background: var(--bg-input);
  border-radius: var(--radius-sm);
  font-size: 12px;
  line-height: 1.5;
  max-height: 300px;
  overflow-y: auto;
}

.step-content pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text);
  font-family: inherit;
}

details[open] .step-summary {
  border-bottom: 1px solid var(--border);
  margin-bottom: 4px;
  padding-bottom: 6px;
}
</style>
