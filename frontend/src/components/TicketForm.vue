<script setup lang="ts">
import { ref, reactive } from 'vue'
import type { TicketDraftEvent } from '../types'
import { createTicket } from '../api'
import { t } from '../i18n'

const props = defineProps<{
  draft: TicketDraftEvent
  vehicleId: string
}>()

const emit = defineEmits<{
  submitted: [ticketId: string]
  close: []
}>()

// Local editable state
const conclusion = ref(props.draft.payload.conclusion ?? '')
const urgency = ref<'low' | 'medium' | 'high'>(props.draft.payload.urgency ?? 'medium')
const operationsText = ref((props.draft.payload.operations as string[])?.join('\n') ?? '')
const sparePartsText = ref((props.draft.payload.spare_parts as string[])?.join('\n') ?? '')

interface RefRow {
  manual: string
  pdf_page: number
}

const references = reactive<RefRow[]>(
  (props.draft.payload.references as RefRow[])?.map(r => ({
    manual: r.manual ?? '',
    pdf_page: r.pdf_page ?? 1,
  })) ?? [{ manual: '', pdf_page: 1 }],
)

function addReference(): void {
  references.push({ manual: '', pdf_page: 1 })
}

function removeReference(idx: number): void {
  if (references.length > 1) {
    references.splice(idx, 1)
  }
}

const submitting = ref(false)
const submitError = ref<string | null>(null)
const successId = ref<string | null>(null)

function validate(): string | null {
  // conclusion non-empty
  if (!conclusion.value.trim()) return t('ticket.validation.conclusion')

  // operations ≥ 1 non-empty line
  const ops = operationsText.value.split('\n').map(l => l.trim()).filter(Boolean)
  if (ops.length === 0) return t('ticket.validation.ops')

  // references ≥ 1 with manual non-empty and page ≥ 1
  for (let i = 0; i < references.length; i++) {
    const r = references[i]
    if (!r.manual.trim()) return t('ticket.validation.ref_manual', { n: String(i + 1) })
    if (r.pdf_page < 1) return t('ticket.validation.ref_page', { n: String(i + 1) })
  }

  return null
}

async function handleSubmit(): Promise<void> {
  submitError.value = null
  const err = validate()
  if (err) {
    submitError.value = err
    return
  }

  submitting.value = true
  try {
    const ops = operationsText.value.split('\n').map(l => l.trim()).filter(Boolean)
    const parts = sparePartsText.value.split('\n').map(l => l.trim()).filter(Boolean)
    const refs = references.map(r => ({
      manual: r.manual.trim(),
      pdf_page: r.pdf_page,
    }))

    const payload: Record<string, unknown> = {
      vehicle_id: props.vehicleId,
      session_id: props.draft.session_id,
      anomaly_type: String(props.draft.payload.anomaly_type),
      conclusion: conclusion.value.trim(),
      urgency: urgency.value,
      operations: ops,
      spare_parts: parts,
      references: refs,
    }

    const result = await createTicket(payload)
    successId.value = result.ticket_id
    emit('submitted', result.ticket_id)
  } catch (e: unknown) {
    if (e instanceof Error && 'status' in e) {
      submitError.value = e.message || `HTTP ${e.status}`
    } else if (e instanceof Error) {
      submitError.value = e.message
    } else {
      submitError.value = t('ticket.error.create')
    }
  } finally {
    submitting.value = false
  }
}

const urgencyLabels: Record<string, string> = {
  low: t('ticket.urgency.low'),
  medium: t('ticket.urgency.medium'),
  high: t('ticket.urgency.high'),
}
</script>

<template>
  <div v-if="successId" class="ticket-success panel">
    <p class="success-text">{{ t('ticket.success', { id: successId }) }}</p>
    <button class="primary" @click="emit('close')">{{ t('ticket.close') }}</button>
  </div>

  <form v-else class="ticket-form" @submit.prevent="handleSubmit">
    <!-- Readonly chips -->
    <div class="readonly-chips">
      <span class="chip readonly-chip">Тип: {{ draft.payload.anomaly_type }}</span>
      <span class="chip readonly-chip mono">{{ draft.session_id }}</span>
    </div>

    <!-- Conclusion -->
    <div class="field">
      <label class="label" for="ticket-conclusion">{{ t('ticket.conclusion.label') }}</label>
      <textarea
        id="ticket-conclusion"
        v-model="conclusion"
        rows="3"
        required
        :placeholder="t('ticket.conclusion.placeholder')"
      />
    </div>

    <!-- Urgency -->
    <div class="field">
      <label class="label" for="ticket-urgency">{{ t('ticket.urgency.label') }}</label>
      <select id="ticket-urgency" v-model="urgency">
        <option value="low">{{ urgencyLabels.low }}</option>
        <option value="medium">{{ urgencyLabels.medium }}</option>
        <option value="high">{{ urgencyLabels.high }}</option>
      </select>
      <p v-if="draft.priority_rationale" class="field-hint">
        Обоснование приоритета: {{ draft.priority_rationale }}
      </p>
    </div>

    <!-- Operations -->
    <div class="field">
      <label class="label" for="ticket-ops">{{ t('ticket.ops.label') }}</label>
      <textarea
        id="ticket-ops"
        v-model="operationsText"
        rows="3"
        required
        :placeholder="t('ticket.ops.placeholder')"
      />
    </div>

    <!-- Spare parts -->
    <div class="field">
      <label class="label" for="ticket-parts">{{ t('ticket.parts.label') }}</label>
      <textarea
        id="ticket-parts"
        v-model="sparePartsText"
        rows="2"
        :placeholder="t('ticket.parts.placeholder')"
      />
    </div>

    <!-- References -->
    <div class="field">
      <label class="label">{{ t('ticket.refs.label') }}</label>
      <div v-for="(ref, idx) in references" :key="idx" class="ref-row">
        <input
          v-model="ref.manual"
          type="text"
          :placeholder="t('ticket.ref.manual_placeholder')"
          class="ref-manual"
        />
        <input
          v-model.number="ref.pdf_page"
          type="number"
          min="1"
          :placeholder="t('ticket.ref.page_placeholder')"
          class="ref-page"
        />
        <button type="button" class="ref-remove" @click="removeReference(idx)" :title="t('ticket.ref.remove_title')">
          &times;
        </button>
      </div>
      <button type="button" class="add-ref-btn" @click="addReference">
        {{ t('ticket.ref.add') }}
      </button>
    </div>

    <!-- Error strip -->
    <div v-if="submitError" class="error-strip" role="alert">
      {{ submitError }}
    </div>

    <!-- Actions -->
    <div class="form-actions">
      <button type="button" class="primary" :disabled="submitting" @click="handleSubmit">
        {{ submitting ? t('ticket.submitting') : t('ticket.submit') }}
      </button>
      <button type="button" :disabled="submitting" @click="emit('close')">{{ t('ticket.cancel') }}</button>
    </div>
  </form>
</template>

<style scoped>
.ticket-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.readonly-chips {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.readonly-chip {
  background: var(--bg-input);
  border: 1px solid var(--border);
  color: var(--text-dim);
}

.ticket-form .field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.ticket-form textarea,
.ticket-form select {
  background: var(--bg-input);
  color: var(--text);
  border: 0;
  border-radius: var(--radius-sm);
  padding: 5px 8px;
  font-size: 13px;
  font-family: inherit;
}

.ticket-form textarea:focus,
.ticket-form select:focus {
  outline: none;
  border-color: var(--accent);
}

.ref-row {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-bottom: 6px;
}

.ref-manual {
  flex: 1;
}

.ref-page {
  width: 70px;
}

.ref-remove {
  background: var(--bg-input);
  border: 0;
  color: var(--danger);
  font-size: 16px;
  padding: 4px 8px;
  cursor: pointer;
  min-height: auto;
  line-height: 1;
}

.ref-remove:hover {
  color: var(--danger-text);
}

.add-ref-btn {
  background: transparent;
  border: 1px dashed var(--border);
  color: var(--text-dim);
  padding: 4px 12px;
  font-size: 12px;
  cursor: pointer;
  border-radius: var(--radius-sm);
}

.add-ref-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.form-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 4px;
}

.ticket-success {
  text-align: center;
}

.success-text {
  font-size: 15px;
  color: var(--accent);
  margin: 0 0 12px;
}
</style>
