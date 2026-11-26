<script setup lang="ts">
import { ref } from 'vue'
import { t } from '../i18n'
import LocaleSwitcher from '../components/LocaleSwitcher.vue'

defineProps<{
  mustChangePassword: boolean
  error: string | null
}>()

const emit = defineEmits<{
  login: [username: string, password: string]
  changePassword: [oldP: string, newP: string]
  dismissedError: []
}>()

// Login form state
const username = ref('')
const password = ref('')
const loading = ref(false)

// Password change form state
const oldPwd = ref('')
const newPwd = ref('')
const newPwdConfirm = ref('')
const pwdError = ref('')
const pwdLoading = ref(false)

function handleLogin(): void {
  if (!username.value.trim() || !password.value) return
  loading.value = true
  emit('login', username.value.trim(), password.value)
}

function handleChangePassword(): void {
  pwdError.value = ''
  const op = oldPwd.value.trim()
  const np = newPwd.value
  const nc = newPwdConfirm.value

  if (!op || !np || !nc) {
    pwdError.value = t('login.error.fillAll')
    return
  }
  if (np.length < 8) {
    pwdError.value = t('login.error.min8')
    return
  }
  if (np !== nc) {
    pwdError.value = t('login.error.mismatch')
    return
  }
  pwdLoading.value = true
  emit('changePassword', op, np)
}

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

      <!-- Login form (always visible) -->
      <form v-if="!mustChangePassword" class="login-form" @submit.prevent="handleLogin">
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

        <button class="primary" type="submit" :disabled="loading" style="width: 100%; margin-top: 12px;">
          {{ loading ? t('login.submitting') : t('login.submit') }}
        </button>
      </form>

      <!-- Password change form (shown after login when must_change_password) -->
      <form v-else class="pwd-change-form" @submit.prevent="handleChangePassword">
        <h2>{{ t('login.change.title') }}</h2>
        <p class="field-hint" style="margin-bottom: 12px;">
          {{ t('login.change.hint') }}
        </p>

        <div class="field">
          <label class="label" for="pwd-old">{{ t('login.change.old') }}</label>
          <input
            id="pwd-old"
            v-model="oldPwd"
            type="password"
            required
            autocomplete="current-password"
          />
        </div>

        <div class="field">
          <label class="label" for="pwd-new">{{ t('login.change.new') }}</label>
          <input
            id="pwd-new"
            v-model="newPwd"
            type="password"
            required
            autocomplete="new-password"
            :placeholder="t('login.change.new.min')"
          />
        </div>

        <div class="field">
          <label class="label" for="pwd-confirm">{{ t('login.change.repeat') }}</label>
          <input
            id="pwd-confirm"
            v-model="newPwdConfirm"
            type="password"
            required
            autocomplete="new-password"
          />
        </div>

        <p v-if="pwdError" class="error-text" style="margin: 8px 0; font-size: 13px;">
          {{ pwdError }}
        </p>

        <button class="primary" type="submit" :disabled="pwdLoading" style="width: 100%; margin-top: 12px;">
          {{ pwdLoading ? t('login.change.saving') : t('login.change.save') }}
        </button>
      </form>

      <p class="field-hint login-hint">
        {{ t('login.adminHint') }}
      </p>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: calc(100vh - 60px);
  padding: 24px 16px;
}

.login-card {
  width: 100%;
  max-width: 400px;
  position: relative;
}

.login-form,
.pwd-change-form {
  display: flex;
  flex-direction: column;
}

.locale-switcher {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 10;
}

.login-hint {
  margin-top: 16px;
  color: var(--text-dim);
  font-size: 12px;
  line-height: 1.4;
}
</style>
