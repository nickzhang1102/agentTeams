<template>
  <div class="agent-portrait" :style="containerStyle">
    <img
      v-if="avatarSrc && !imgError"
      :src="avatarSrc"
      :alt="name"
      :style="imgStyle"
      @error="onImgError"
      loading="lazy"
    />
    <div
      v-else
      class="portrait-fallback"
      :style="fallbackStyle"
    >
      {{ initial }}
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { getAvatarUrl, getCategoryColor, getInitial } from '@/utils/avatar'

const props = defineProps({
  portraitUrl: { type: String, default: null },
  agentId: { type: String, required: true },
  name: { type: String, default: '' },
  category: { type: String, default: 'default' },
  size: { type: Number, default: 64 },
})

const imgError = ref(false)

const avatarSrc = computed(() => {
  if (props.portraitUrl && isValidImageUrl(props.portraitUrl)) return props.portraitUrl
  return getAvatarUrl(props.agentId, props.category)
})

function isValidImageUrl(url) {
  try {
    const parsed = new URL(url)
    return parsed.protocol === 'http:' || parsed.protocol === 'https:'
  } catch {
    return false
  }
}

const initial = computed(() => getInitial(props.name))

const containerStyle = computed(() => ({
  width: `${props.size}px`,
  height: `${props.size}px`,
  flexShrink: '0',
}))

const imgStyle = computed(() => ({
  width: '100%',
  height: '100%',
  borderRadius: '50%',
  objectFit: 'cover',
}))

const fallbackStyle = computed(() => ({
  width: '100%',
  height: '100%',
  borderRadius: '50%',
  backgroundColor: getCategoryColor(props.category),
  color: '#fff',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  fontSize: `${Math.round(props.size * 0.4)}px`,
  fontWeight: '600',
}))

function onImgError() {
  imgError.value = true
}
</script>

<style scoped>
.agent-portrait {
  display: inline-block;
}
.portrait-fallback {
  user-select: none;
}
</style>
