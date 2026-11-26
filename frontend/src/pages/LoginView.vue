<script setup lang="ts">
import { ref } from 'vue'

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
    pwdError.value = 'Заполните все поля'
    return
  }
  if (np.length < 8) {
    pwdError.value = 'Новый пароль: минимум 8 символов'
    return
  }
  if (np !== nc) {
    pwdError.value = 'Пароли не совпадают'
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
      <h1>Цифровой механик</h1>

      <!-- Error strip -->
      <div v-if="error" class="error-strip" @click="dismissError" role="alert">
        {{ error }}
      </div>

      <!-- Login form (always visible) -->
      <form v-if="!mustChangePassword" class="login-form" @submit.prevent="handleLogin">
        <div class="field">
          <label class="label" for="login-user">Имя пользователя</label>
          <input
            id="login-user"
            v-model="username"
            type="text"
            autocomplete="username"
            required
            placeholder="Введите имя"
          />
        </div>

        <div class="field">
          <label class="label" for="login-pass">Пароль</label>
          <input
            id="login-pass"
            v-model="password"
            type="password"
            autocomplete="current-password"
            required
            placeholder="Введите пароль"
          />
        </div>

        <button class="primary" type="submit" :disabled="loading" style="width: 100%; margin-top: 12px;">
          {{ loading ? 'Вход…' : 'Войти' }}
        </button>
      </form>

      <!-- Password change form (shown after login when must_change_password) -->
      <form v-else class="pwd-change-form" @submit.prevent="handleChangePassword">
        <h2>Смените пароль</h2>
        <p class="field-hint" style="margin-bottom: 12px;">
          Для продолжения установите новый пароль.
        </p>

        <div class="field">
          <label class="label" for="pwd-old">Старый пароль</label>
          <input
            id="pwd-old"
            v-model="oldPwd"
            type="password"
            required
            autocomplete="current-password"
          />
        </div>

        <div class="field">
          <label class="label" for="pwd-new">Новый пароль</label>
          <input
            id="pwd-new"
            v-model="newPwd"
            type="password"
            required
            autocomplete="new-password"
            placeholder="Минимум 8 символов"
          />
        </div>

        <div class="field">
          <label class="label" for="pwd-confirm">Повторите новый пароль</label>
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
          {{ pwdLoading ? 'Сохранение…' : 'Сохранить пароль' }}
        </button>
      </form>

      <p class="field-hint login-hint">
        Стартовый пароль admin печатается в консоль сервера при первом запуске.
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
}

.login-form,
.pwd-change-form {
  display: flex;
  flex-direction: column;
}

.login-hint {
  margin-top: 16px;
  color: var(--text-dim);
  font-size: 12px;
  line-height: 1.4;
}
</style>
