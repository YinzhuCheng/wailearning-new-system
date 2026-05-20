<template>
  <div ref="shellRef" class="dual-horizontal-scroll">
    <div
      v-if="showTopScrollbar"
      ref="topScrollbarRef"
      class="dual-horizontal-scroll__top"
      data-testid="dual-horizontal-scroll-top"
      @scroll="handleTopScrollbarScroll"
    >
      <div class="dual-horizontal-scroll__spacer" :style="{ width: `${spacerWidth}px` }" />
    </div>
    <div class="dual-horizontal-scroll__content">
      <slot />
    </div>
  </div>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, onUpdated, ref } from 'vue'

const props = defineProps({
  /**
   * CSS selector used to locate the real horizontal scroll container inside the slot content.
   * If nothing matches, the component falls back to the slot wrapper itself.
   */
  targetSelector: {
    type: String,
    default: '.dual-scroll-target, .el-scrollbar__wrap, .el-table__body-wrapper'
  }
})

const shellRef = ref(null)
const topScrollbarRef = ref(null)
const spacerWidth = ref(0)
const showTopScrollbar = ref(false)

let mutationObserver = null
let resizeObserver = null
let targetElement = null
let syncSource = ''

function resolveContentWrapper() {
  return shellRef.value?.querySelector('.dual-horizontal-scroll__content') || null
}

function resolveTargetElement() {
  const contentWrapper = resolveContentWrapper()
  if (!contentWrapper) {
    return null
  }
  return contentWrapper.querySelector(props.targetSelector) || contentWrapper
}

function handleTargetScroll() {
  if (!topScrollbarRef.value || !targetElement || syncSource === 'top') {
    return
  }
  syncSource = 'target'
  topScrollbarRef.value.scrollLeft = targetElement.scrollLeft
  requestAnimationFrame(() => {
    syncSource = ''
  })
}

function bindTargetElement(nextTarget) {
  if (targetElement === nextTarget) {
    return
  }
  if (targetElement) {
    targetElement.removeEventListener('scroll', handleTargetScroll)
  }
  targetElement = nextTarget
  if (targetElement) {
    targetElement.addEventListener('scroll', handleTargetScroll, { passive: true })
    resizeObserver?.observe(targetElement)
  }
}

function updateMetrics() {
  nextTick(() => {
    const nextTarget = resolveTargetElement()
    bindTargetElement(nextTarget)

    if (!nextTarget || !topScrollbarRef.value) {
      spacerWidth.value = 0
      showTopScrollbar.value = false
      return
    }

    const width = Math.ceil(nextTarget.scrollWidth)
    const clientWidth = Math.ceil(nextTarget.clientWidth)
    spacerWidth.value = width
    showTopScrollbar.value = width > clientWidth + 1

    if (showTopScrollbar.value) {
      topScrollbarRef.value.scrollLeft = nextTarget.scrollLeft
    }
  })
}

function handleTopScrollbarScroll() {
  if (!topScrollbarRef.value || !targetElement || syncSource === 'target') {
    return
  }
  syncSource = 'top'
  targetElement.scrollLeft = topScrollbarRef.value.scrollLeft
  requestAnimationFrame(() => {
    syncSource = ''
  })
}

onMounted(() => {
  resizeObserver = new ResizeObserver(() => {
    updateMetrics()
  })
  if (shellRef.value) {
    resizeObserver.observe(shellRef.value)
  }

  mutationObserver = new MutationObserver(() => {
    updateMetrics()
  })
  if (shellRef.value) {
    mutationObserver.observe(shellRef.value, {
      childList: true,
      subtree: true,
      attributes: true
    })
  }

  window.addEventListener('resize', updateMetrics)
  updateMetrics()
})

onUpdated(() => {
  updateMetrics()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', updateMetrics)
  mutationObserver?.disconnect()
  resizeObserver?.disconnect()
  if (targetElement) {
    targetElement.removeEventListener('scroll', handleTargetScroll)
  }
})
</script>

<style scoped>
.dual-horizontal-scroll {
  width: 100%;
  max-width: 100%;
}

.dual-horizontal-scroll__top {
  overflow-x: auto;
  overflow-y: hidden;
  max-width: 100%;
  margin-bottom: 8px;
}

.dual-horizontal-scroll__spacer {
  height: 1px;
}

.dual-horizontal-scroll__content {
  width: 100%;
  max-width: 100%;
  min-width: 0;
}
</style>
