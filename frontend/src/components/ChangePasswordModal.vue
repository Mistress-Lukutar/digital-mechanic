<script setup lang="ts">
import { ref } from 'vue'
import { t } from '../i18n'

const props = defineProps<{
  error: string | null
  loading: boolean
}>()

const emit = defineEmits<{
  submit: [oldPassword: string, newPassword: string]
}>()

const oldPwd = ref('')
const newPwd = ref('')
const newPwdConfirm = ref('')
const localError = ref('')

function handleSubmit(): void {
  localError.value = ''

  if (!oldPwd.value || !newPwd.value || !newPwdConfirm.value) {
    localError.value = t('login.error.fillAll')
    return
  }
  if (newPwd.value.length < 8) {
    localError.value = t('login.error.min8')
    return
  }
  if (newPwd.value !== newPwdConfirm.value) {
    localError.value = t('login.error.mismatch')
    return
  }

  emit('submit', oldPwd.value.trim(), newPwd.value)
}
</script>

<template>
  <Teleport to="body">
    <div class="modal-overlay">
      <div class="modal" role="dialog" aria-modal="true" :aria-label="t('login.change.title')">
        <div class="modal-header"><h3>{{ t('login.change.title') }}</h3></div>
        <div class="modal-body">
          <p class="pwd-hint">{{ t('login.change.hint') }}</p>
          <form class="pwd-form" @submit.prevent="handleSubmit">
            <div class="field">
              <label class="label" for="pwd-old">{{ t('login.change.old') }}</label>
              <input
                id="pwd-old"
                v-model="oldPwd"
                type="password"
                autocomplete="current-password"
                required
              />
            </div>

            <div class="field">
              <label class="label" for="pwd-new">{{ t('login.change.new') }}</label>
              <input
                id="pwd-new"
                v-model="newPwd"
                type="password"
                autocomplete="new-password"
                :placeholder="t('login.change.new.min')"
                required
              />
            </div>

            <div class="field">
              <label class="label" for="pwd-confirm">{{ t('login.change.repeat') }}</label>
              <input
                id="pwd-confirm"
                v-model="newPwdConfirm"
                type="password"
                autocomplete="new-password"
                required
              />
            </div>

            <p v-if="localError" class="error-text" role="alert">{{ localError }}</p>
            <p v-else-if="props.error" class="error-text" role="alert">{{ props.error }}</p>

            <button
              class="primary"
              type="submit"
              :disabled="props.loading"
              style="width: 100%; margin-top: 12px;"
            >
              {{ props.loading ? t('login.change.saving') : t('login.change.save') }}
            </button>
          </form>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.pwd-hint {
  font-size: 12px;
  color: var(--text-dim);
  margin: 0 0 8px;
}

.pwd-form {
  display: flex;
  flex-direction: column;
}

.error-text {
  margin: 8px 0;
}
</style>
