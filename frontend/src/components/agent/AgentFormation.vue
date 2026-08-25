<template>
  <div class="agent-formation">
    <div
      v-for="tier in tiers"
      :key="tier.priority"
      class="tier-row"
      :class="{
        'tier-row--empty': tier.agents.length === 0,
        'tier-row--drag-over': dragOverTier === tier.priority,
      }"
    >
      <!-- 排标题 -->
      <div class="tier-header">
        <span class="tier-badge" :style="{ background: tier.color }">
          {{ tier.label }}
        </span>
        <span class="tier-priority">P{{ tier.priority }}</span>
      </div>

      <!-- 可拖拽卡片区域 -->
      <div
        :ref="el => setTierRef(tier.priority, el)"
        class="tier-cards"
        :class="{ 'tier-cards--empty-placeholder': tier.agents.length === 0 }"
        :data-tier-priority="tier.priority"
      >
        <div
          v-for="agent in tier.agents"
          :key="agent.agent_id"
          class="tier-card-wrapper"
          :class="{ 'tier-card-wrapper--locked': !canDrag(agent) }"
          :data-agent-id="agent.agent_id"
        >
          <AgentCard
            :agent="agent"
            :mode="mode"
            :show-actions="mode === 'admin'"
            :show-toggle="mode === 'admin'"
            layout="vertical"
            @click="$emit('cardClick', agent)"
            @edit="$emit('edit', agent)"
            @delete="$emit('delete', agent)"
            @toggle="$emit('toggle', agent)"
          />
        </div>

        <!-- 空排占位 -->
        <div v-if="tier.agents.length === 0" class="tier-empty">
          <span class="tier-empty-text">可拖入</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import Sortable from 'sortablejs'
import AgentCard from './AgentCard.vue'

const props = defineProps({
  agents: { type: Array, required: true },
  canDrag: { type: Function, default: () => false },
  mode: { type: String, default: 'user' },
})

const emit = defineEmits(['cardClick', 'edit', 'delete', 'toggle', 'priorityChange'])

// Tier 定义：priority 是每个 tier 的代表值，upper 是该 tier 覆盖的 priority 上界
const TIER_DEFS = [
  { tier: 1, priority: 10, upper: 15, label: '第1排', color: '#409eff' },
  { tier: 2, priority: 20, upper: 25, label: '第2排', color: '#67c23a' },
  { tier: 3, priority: 30, upper: 35, label: '第3排', color: '#e6a23c' },
  { tier: 4, priority: 40, upper: 45, label: '第4排', color: '#f56c6c' },
  { tier: 5, priority: 50, upper: Infinity, label: '第5排', color: '#909399' },
]

function priorityToTierIndex(p) {
  for (let i = 0; i < TIER_DEFS.length; i++) {
    if (p < TIER_DEFS[i].upper) return i
  }
  return TIER_DEFS.length - 1
}

const dragOverTier = ref(null)
const tiers = ref(TIER_DEFS.map(d => ({ ...d, agents: [] })))
const tierRefs = {}
const sortableInstances = []

function setTierRef(priority, el) {
  if (el) tierRefs[priority] = el
}

function rebuildTiers(agents) {
  const buckets = TIER_DEFS.map(() => [])
  for (const agent of agents) {
    const p = agent.priority ?? 50
    buckets[priorityToTierIndex(p)].push(agent)
  }
  for (let i = 0; i < TIER_DEFS.length; i++) {
    tiers.value[i].agents = buckets[i]
  }
}

watch(() => props.agents, (agents) => rebuildTiers(agents), { immediate: true })

function findAgentById(agentId) {
  for (const tier of tiers.value) {
    const found = tier.agents.find(a => a.agent_id === agentId)
    if (found) return found
  }
  return null
}

function findTierByPriority(priority) {
  return tiers.value.find(t => t.priority === priority)
}

function initSortable() {
  sortableInstances.forEach(s => s.destroy())
  sortableInstances.length = 0

  const groupName = props.mode === 'admin' ? 'agent-formation-admin' : 'agent-formation-user'

  for (const tier of tiers.value) {
    const el = tierRefs[tier.priority]
    if (!el) continue

    const sortable = Sortable.create(el, {
      group: { name: groupName, pull: true, put: true },
      animation: 200,
      ghostClass: 'drag-ghost',
      chosenClass: 'drag-chosen',
      dragClass: 'drag-drag',
      draggable: '.tier-card-wrapper',
      handle: '.tier-card-wrapper',

      onEnd(evt) {
        dragOverTier.value = null

        const agentId = evt.item.dataset.agentId
        const fromPriority = parseInt(evt.from.dataset.tierPriority)
        const toPriority = parseInt(evt.to.dataset.tierPriority)

        if (fromPriority === toPriority && evt.oldIndex === evt.newIndex) return

        const agent = findAgentById(agentId)
        if (!agent) return

        const fromTier = findTierByPriority(fromPriority)
        const toTier = findTierByPriority(toPriority)

        // 同步本地 tiers 数据
        const idx = fromTier.agents.findIndex(a => a.agent_id === agentId)
        if (idx !== -1) fromTier.agents.splice(idx, 1)
        toTier.agents.splice(evt.newIndex, 0, agent)

        // 跨排拖拽需持久化新的 priority 值
        if (fromPriority !== toPriority) {
          emit('priorityChange', { agentId, priority: toPriority, position: evt.newIndex })
        }
      },

      onChange(evt) {
        const toPriority = parseInt(evt.to.dataset.tierPriority)
        dragOverTier.value = toPriority
      },
    })

    sortableInstances.push(sortable)
  }
}

onMounted(() => {
  nextTick(() => initSortable())
})

watch(() => props.agents, () => {
  nextTick(() => initSortable())
}, { flush: 'post' })

onBeforeUnmount(() => {
  sortableInstances.forEach(s => s.destroy())
})
</script>

<style scoped>
.agent-formation {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.tier-row {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 16px;
  border-radius: 12px;
  background: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color-lighter);
  transition: background 0.2s, border-color 0.2s;
}

.tier-row--empty {
  border-style: dashed;
  opacity: 0.6;
  min-height: 80px;
  align-items: center;
}

.tier-row--drag-over {
  background: rgba(64, 158, 255, 0.06);
  border-color: var(--el-color-primary-light-5);
}

.tier-header {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  min-width: 56px;
  flex-shrink: 0;
  padding-top: 4px;
}

.tier-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 4px 10px;
  border-radius: 6px;
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
}

.tier-priority {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  font-family: monospace;
}

.tier-cards {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  flex: 1;
  min-width: 0;
  min-height: 40px;
}

.tier-cards--empty-placeholder {
  min-height: 60px;
}

.tier-card-wrapper {
  width: 220px;
  flex-shrink: 0;
  cursor: grab !important;
}
.tier-card-wrapper:active {
  cursor: grabbing !important;
}
.tier-card-wrapper :deep(.agent-card) {
  cursor: inherit;
}

.tier-card-wrapper--locked {
  cursor: not-allowed !important;
  opacity: 0.7;
}
.tier-card-wrapper--locked :deep(.agent-card) {
  cursor: not-allowed !important;
  pointer-events: none;
}
.tier-card-wrapper--locked :deep(.agent-card:hover) {
  transform: none;
}

.tier-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 60px;
  width: 100%;
}

.tier-empty-text {
  font-size: 13px;
  color: var(--el-text-color-placeholder);
}

/* ========== 拖拽状态样式 ========== */

/* 拖拽中的幽灵卡（原位占位） */
:deep(.drag-ghost) {
  opacity: 0.4;
  border: 2px dashed var(--el-color-primary-light-5);
  border-radius: 8px;
  background: var(--el-color-primary-light-9);
}

/* 被选中准备拖动的卡片 */
:deep(.drag-chosen) {
  cursor: grabbing;
}

/* 正在拖动的浮动卡 */
:deep(.drag-drag) {
  opacity: 0.85;
  transform: scale(1.03);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
  border-radius: 8px;
  cursor: grabbing;
  z-index: 9999;
}

@media (max-width: 767px) {
  .tier-row {
    flex-direction: column;
    gap: 10px;
    padding: 12px;
  }
  .tier-header {
    flex-direction: row;
    min-width: auto;
    gap: 8px;
  }
  .tier-card-wrapper {
    width: 100%;
  }
}
</style>
