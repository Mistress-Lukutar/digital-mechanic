import { ref, readonly } from 'vue'
import type { UserRole } from '../types'
import { login as apiLogin, getMe, changePassword as apiChangePassword, logoutToken, setAuthToken } from '../api'

const STORAGE_KEY = 'dm_auth'

interface StoredAuth {
  token: string
  username: string
  role: UserRole
  mustChangePassword: boolean
}

const _token = ref<string | null>(null)
const _username = ref<string>('')
const _role = ref<UserRole>('user')
const _mustChangePassword = ref(false)

function store(): StoredAuth | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    return JSON.parse(raw) as StoredAuth
  } catch {
    return null
  }
}

function persist(auth: StoredAuth): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(auth))
}

function clearStore(): void {
  localStorage.removeItem(STORAGE_KEY)
  _token.value = null
  _username.value = ''
  _role.value = 'user'
  _mustChangePassword.value = false
}

export function useAuth() {
  async function login(username: string, password: string): Promise<void> {
    const result = await apiLogin(username, password)
    _token.value = result.token
    _username.value = result.username
    _role.value = result.role
    _mustChangePassword.value = result.must_change_password
    persist({
      token: result.token,
      username: result.username,
      role: result.role,
      mustChangePassword: result.must_change_password,
    })
  }

  async function changePassword(oldP: string, newP: string): Promise<void> {
    await apiChangePassword(oldP, newP)
    _mustChangePassword.value = false
    // Update stored auth without changing token
    const s = store()
    if (s) {
      s.mustChangePassword = false
      persist(s)
    }
  }

  function logout(): void {
    clearStore()
    logoutToken()
  }

  async function restore(): Promise<boolean> {
    const saved = store()
    if (!saved) return false
    setAuthToken(saved.token)
    try {
      const me = await getMe()
      _token.value = saved.token
      _username.value = me.username
      _role.value = me.role
      _mustChangePassword.value = me.must_change_password
      // Refresh stored profile in case role changed server-side
      persist({
        token: saved.token,
        username: me.username,
        role: me.role,
        mustChangePassword: me.must_change_password,
      })
      return true
    } catch {
      clearStore()
      logoutToken()
      return false
    }
  }

  return {
    token: readonly(_token),
    username: readonly(_username),
    role: readonly(_role),
    mustChangePassword: readonly(_mustChangePassword),
    login,
    changePassword,
    logout,
    restore,
  }
}

// Module singleton — exported once.
export const auth = useAuth()
