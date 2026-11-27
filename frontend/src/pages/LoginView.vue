<script setup lang="ts">
import { ref, watch } from 'vue'
import { t } from '../i18n'
import LocaleSwitcher from '../components/LocaleSwitcher.vue'

const props = defineProps<{
  error: string | null
}>()

const emit = defineEmits<{
  login: [username: string, password: string]
  dismissedError: []
}>()

// Login form state
const username = ref('')
const password = ref('')
const loading = ref(false)
const consent = ref(false)

function handleLogin(): void {
  if (!username.value.trim() || !password.value) return
  loading.value = true
  emit('login', username.value.trim(), password.value)
}

// The parent owns the async login call; a reported error means the
// attempt finished — re-enable the submit button so the user can retry.
watch(
  () => props.error,
  (error) => {
    if (error) loading.value = false
  },
)

function dismissError(): void {
  emit('dismissedError')
}
</script>

<template>
  <div class="login-page">
    <div class="login-card panel">
      <LocaleSwitcher />

      <h1>{{ t('app.title') }}</h1>

      <!-- Error strip -->
      <div v-if="error" class="error-strip" @click="dismissError" role="alert">
        {{ error }}
      </div>

      <!-- Login form -->
      <form class="login-form" @submit.prevent="handleLogin">
        <div class="field">
          <label class="label" for="login-user">{{ t('login.username') }}</label>
          <input
            id="login-user"
            v-model="username"
            type="text"
            autocomplete="username"
            required
            :placeholder="t('login.placeholder.username')"
          />
        </div>

        <div class="field">
          <label class="label" for="login-pass">{{ t('login.password') }}</label>
          <input
            id="login-pass"
            v-model="password"
            type="password"
            autocomplete="current-password"
            required
            :placeholder="t('login.placeholder.password')"
          />
        </div>

        <div class="field consent-field">
          <input id="login-consent" type="checkbox" v-model="consent" required />
          <label class="label" for="login-consent">{{ t('login.consent') }}</label>
        </div>

        <button class="primary" type="submit" :disabled="loading || !consent" style="width: 100%; margin-top: 12px;">
          {{ loading ? t('login.submitting') : t('login.submit') }}
        </button>
      </form>

    </div>
  </div>
</template>

<style scoped>
.login-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: calc(100vh - 60px);
  min-height: calc(100dvh - 60px);
  padding: 24px 16px;
}

.login-card {
  width: 100%;
  max-width: 400px;
  position: relative;
}

.login-form {
  display: flex;
  flex-direction: column;
}

.locale-switcher {
  justify-content: center;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.consent-field {
  flex-direction: row;
  align-items: flex-start;
  gap: 8px;
}

.consent-field input[type='checkbox'] {
  flex-shrink: 0;
  margin-top: 2px;
}
</style>
