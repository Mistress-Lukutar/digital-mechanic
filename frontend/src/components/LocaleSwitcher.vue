<script setup lang="ts">
import { locale, setLocale, LOCALE_OPTIONS } from '../i18n'

function isActive(opt: (typeof LOCALE_OPTIONS)[number]): boolean {
  return locale.value === opt.value
}
</script>

<template>
  <div class="locale-switcher" role="group" aria-label="Язык / Language">
    <button
      v-for="opt in LOCALE_OPTIONS"
      :key="opt.value"
      type="button"
      :class="{ active: isActive(opt) }"
      :aria-pressed="isActive(opt)"
      :aria-label="opt.native"
      @click="setLocale(opt.value)"
    >
      <svg class="flag" viewBox="0 0 24 16" width="21" height="14" aria-hidden="true">
        <!-- ru -->
        <template v-if="opt.value === 'ru'">
          <rect x="0" y="0" width="24" height="5.33" fill="#ffffff" />
          <rect x="0" y="5.33" width="24" height="5.34" fill="#0039A6" />
          <rect x="0" y="10.67" width="24" height="5.33" fill="#D52B1E" />
        </template>
        <!-- kk -->
        <template v-if="opt.value === 'kk'">
          <rect x="0" y="0" width="24" height="16" fill="#00AFCA" />
          <circle cx="12" cy="8" r="4" fill="#FEC50C" />
        </template>
        <!-- uz -->
        <template v-if="opt.value === 'uz'">
          <rect x="0" y="0" width="24" height="5.33" fill="#0099B5" />
          <rect x="0" y="5.33" width="24" height="1" fill="#CE1126" />
          <rect x="0" y="6.33" width="24" height="4" fill="#ffffff" />
          <rect x="0" y="10.33" width="24" height="1" fill="#CE1126" />
          <rect x="0" y="11.33" width="24" height="4.67" fill="#1EB53A" />
        </template>
        <!-- hi -->
        <template v-if="opt.value === 'hi'">
          <rect x="0" y="0" width="24" height="5.33" fill="#FF9933" />
          <rect x="0" y="5.33" width="24" height="5.34" fill="#ffffff" />
          <circle cx="12" cy="8" r="1.8" fill="#000080" />
          <rect x="0" y="10.67" width="24" height="5.33" fill="#138808" />
        </template>
      </svg>
      <span class="label">{{ opt.native }}</span>
    </button>
  </div>
</template>

<style scoped>
.locale-switcher {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}

.locale-switcher button {
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

.locale-switcher button:hover {
  background: var(--bg-input);
  color: var(--text);
}

.locale-switcher button.active {
  background: var(--bg-input);
  border-color: var(--accent);
  color: var(--text);
}

.flag {
  flex-shrink: 0;
  /* subtle border so white stripe is visible on light backgrounds */
  outline: 1px solid rgba(0, 0, 0, 0.25);
  outline-offset: -1px;
}

.label {
  font-size: 13px;
  line-height: 1;
}
</style>
