<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { locale, setLocale, LOCALE_OPTIONS } from '../i18n'

const open = ref(false)
const root = ref<HTMLDivElement | null>(null)

function isActive(opt: (typeof LOCALE_OPTIONS)[number]): boolean {
  return locale.value === opt.value
}

function toggleOpen(): void {
  open.value = !open.value
}

function selectLocale(opt: (typeof LOCALE_OPTIONS)[number]): void {
  setLocale(opt.value)
  open.value = false
}

function findNative(value: string): string {
  const found = LOCALE_OPTIONS.find(o => o.value === value)
  return found ? found.native : ''
}

// Close on outside click
function onDocumentClick(event: MouseEvent): void {
  if (root.value && !root.value.contains(event.target as Node)) {
    open.value = false
  }
}

// Close on Escape
function onDocumentKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') {
    open.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
  document.addEventListener('keydown', onDocumentKeydown)
})

onUnmounted(() => {
  document.removeEventListener('click', onDocumentClick)
  document.removeEventListener('keydown', onDocumentKeydown)
})
</script>

<template>
  <div class="locale-switcher" role="group" aria-label="Язык / Language" ref="root">
    <!-- Trigger button -->
    <button
      type="button"
      aria-haspopup="menu"
      :aria-expanded="open"
      :aria-label="findNative(locale)"
      class="trigger"
      @click="toggleOpen"
    >
      <!-- Globe icon: circle + vertical ellipse (meridian) + horizontal line (equator) -->
      <svg class="globe-icon" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
        <circle cx="8" cy="8" r="7" stroke="currentColor" fill="none" stroke-width="1.2" />
        <ellipse cx="8" cy="8" rx="3" ry="7" stroke="currentColor" fill="none" stroke-width="1.2" />
        <line x1="1" y1="8" x2="15" y2="8" stroke="currentColor" stroke-width="1.2" />
      </svg>
      <span class="trigger-label">{{ locale.toUpperCase() }}</span>
      <span class="caret">▾</span>
    </button>

    <!-- Dropdown menu -->
    <div v-if="open" class="menu" role="menu">
      <button
        v-for="opt in LOCALE_OPTIONS"
        :key="opt.value"
        type="button"
        role="menuitem"
        :class="{ active: isActive(opt) }"
        @click="selectLocale(opt)"
      >
        <!-- Flag SVGs (copied from original component) -->
        <svg v-if="opt.value === 'ru'" class="flag" viewBox="0 0 24 16" width="24" height="16" aria-hidden="true">
          <rect x="0" y="0" width="24" height="5.33" fill="#ffffff" />
          <rect x="0" y="5.33" width="24" height="5.34" fill="#0039A6" />
          <rect x="0" y="10.67" width="24" height="5.33" fill="#D52B1E" />
        </svg>
        <svg v-else-if="opt.value === 'kk'" class="flag" viewBox="0 0 24 16" width="24" height="16" aria-hidden="true">
          <rect x="0" y="0" width="24" height="16" fill="#00AFCA" />
          <circle cx="12" cy="8" r="4" fill="#FEC50C" />
        </svg>
        <svg v-else-if="opt.value === 'uz'" class="flag" viewBox="0 0 24 16" width="24" height="16" aria-hidden="true">
          <rect x="0" y="0" width="24" height="5.33" fill="#0099B5" />
          <rect x="0" y="5.33" width="24" height="1" fill="#CE1126" />
          <rect x="0" y="6.33" width="24" height="4" fill="#ffffff" />
          <rect x="0" y="10.33" width="24" height="1" fill="#CE1126" />
          <rect x="0" y="11.33" width="24" height="4.67" fill="#1EB53A" />
        </svg>
        <svg v-else-if="opt.value === 'hi'" class="flag" viewBox="0 0 24 16" width="24" height="16" aria-hidden="true">
          <rect x="0" y="0" width="24" height="5.33" fill="#FF9933" />
          <rect x="0" y="5.33" width="24" height="5.34" fill="#ffffff" />
          <circle cx="12" cy="8" r="1.8" fill="#000080" />
          <rect x="0" y="10.67" width="24" height="5.33" fill="#138808" />
        </svg>
        <span class="item-label">{{ opt.native }}</span>
        <span v-if="isActive(opt)" class="checkmark">✓</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.locale-switcher {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  position: relative;
}

/* ---- Trigger button ---- */
.trigger {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border-radius: 8px;
  font-size: 13px;
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text-dim);
  cursor: pointer;
  min-height: auto;
}

.trigger:hover {
  background: var(--bg-input);
  color: var(--text);
}

.globe-icon {
  flex-shrink: 0;
}

.trigger-label {
  font-size: 13px;
  line-height: 1;
}

.caret {
  font-size: 10px;
  line-height: 1;
  color: var(--text-dim);
}

/* ---- Menu ---- */
.menu {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  min-width: 190px;
  z-index: 50;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.25);
  padding: 4px;
}

.menu button {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 6px 8px;
  border: 0;
  background: transparent;
  border-radius: var(--radius-sm, 6px);
  color: var(--text);
  cursor: pointer;
  text-align: left;
  font-size: 13px;
}

.menu button:hover {
  background: var(--bg-input);
}

.menu button.active {
  color: var(--accent);
}

.flag {
  flex-shrink: 0;
  outline: 1px solid rgba(0, 0, 0, 0.25);
  outline-offset: -1px;
}

.item-label {
  flex: 1;
  font-size: 13px;
  line-height: 1;
}

.checkmark {
  color: var(--accent);
  font-size: 14px;
  line-height: 1;
  flex-shrink: 0;
}
</style>
