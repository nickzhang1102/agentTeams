<template>
  <el-card
    class="agent-card"
    :class="{ 'agent-card--horizontal': isHorizontal }"
    shadow="hover"
    @click="$emit('click', agent)"
  >
    <div class="card-body" :class="{ 'card-body--horizontal': isHorizontal }">
      <!-- 头像 -->
      <AgentPortrait
        :portrait-url="agent.portrait_url"
        :agent-id="agent.agent_id"
        :name="displayName"
        :category="primaryCategory"
        :size="isHorizontal ? 48 : 64"
      />

      <!-- 信息区 -->
      <div class="card-info">
        <!-- 名称 -->
        <div class="agent-name">{{ displayName }}</div>
        <div class="agent-id">{{ agent.agent_id }}</div>

        <!-- 标签行 -->
        <div class="agent-badges">
          <el-tag v-if="agent.is_system" size="small" type="info">系统</el-tag>
          <el-tag v-else size="small" type="success">自建</el-tag>
          <el-tag v-if="!agent.is_enabled" size="small" :type="agent.source === 'db' ? 'warning' : 'info'">
            {{ agent.source === 'db' ? '待审核' : '已禁用' }}
          </el-tag>
          <span class="skill-level">
            <span v-for="n in 5" :key="n" class="star" :class="{ active: n <= (agent.skill_level || 3) }">★</span>
          </span>
        </div>

        <!-- 能力标签 -->
        <div v-if="displayCapabilities.length" class="agent-capabilities">
          <el-tag
            v-for="cap in displayCapabilities"
            :key="cap"
            size="small"
            type="info"
            effect="plain"
            class="cap-tag"
          >{{ cap }}</el-tag>
          <span v-if="remainingCaps > 0" class="cap-more">+{{ remainingCaps }}</span>
        </div>

        <!-- 描述（桌面端显示） -->
        <div v-if="!isHorizontal && agent.description" class="agent-desc">
          {{ truncatedDesc }}
        </div>

        <!-- 统计 -->
        <div class="agent-stats">
          <span>调用 {{ agent.total_calls || 0 }} 次</span>
          <span v-if="agent.total_calls">· 成功率 {{ successRate }}%</span>
        </div>
      </div>
    </div>

    <!-- 操作按钮 -->
    <div v-if="showActions" class="card-actions" @click.stop>
      <el-button size="small" @click="$emit('edit', agent)">编辑</el-button>
      <el-button
        v-if="!agent.is_system"
        size="small"
        type="danger"
        @click="$emit('delete', agent)"
      >删除</el-button>
      <el-button
        v-if="showToggle"
        size="small"
        :type="agent.is_enabled ? 'warning' : 'success'"
        @click="$emit('toggle', agent)"
      >{{ agent.is_enabled ? '禁用' : '启用' }}</el-button>
    </div>
  </el-card>
</template>

<script setup>
import { computed } from 'vue'
import AgentPortrait from './AgentPortrait.vue'
import { catalogLabel } from '@/utils/catalog'

const props = defineProps({
  agent: { type: Object, required: true },
  mode: { type: String, default: 'user' }, // admin | user | selector
  showActions: { type: Boolean, default: false },
  showToggle: { type: Boolean, default: false },
  layout: { type: String, default: 'auto' }, // auto | vertical | horizontal
})

defineEmits(['click', 'edit', 'delete', 'toggle'])

const displayName = computed(() => catalogLabel(props.agent))

const isHorizontal = computed(() => {
  if (props.layout === 'horizontal') return true
  if (props.layout === 'vertical') return false
  // auto: 由 CSS 媒体查询控制，这里返回 false 让 CSS 处理
  return false
})

const primaryCategory = computed(() => {
  // 优先使用 DB category 字段
  if (props.agent.category) return props.agent.category
  // Fallback：从 tags 推断（兼容旧文件源数据）
  const tags = props.agent.tags || []
  if (tags.includes('medical')) return 'medical'
  if (tags.includes('finance')) return 'finance'
  if (tags.includes('business')) return 'business'
  if (!props.agent.is_system) return 'custom'
  return 'default'
})

const displayCapabilities = computed(() => {
  const caps = props.agent.capabilities || []
  return caps.slice(0, isHorizontal.value ? 1 : 3)
})

const remainingCaps = computed(() => {
  const caps = props.agent.capabilities || []
  return Math.max(0, caps.length - (isHorizontal.value ? 1 : 3))
})

const truncatedDesc = computed(() => {
  const desc = props.agent.description || ''
  return desc.length > 60 ? desc.slice(0, 57) + '...' : desc
})

const successRate = computed(() => {
  const total = props.agent.total_calls || 0
  if (!total) return 0
  return Math.round(((props.agent.success_calls || 0) / total) * 100)
})
</script>

<style scoped>
.agent-card {
  cursor: pointer;
  transition: transform 0.2s;
}
.agent-card:hover {
  transform: translateY(-2px);
}

.card-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 8px;
}

.card-body--horizontal {
  flex-direction: row;
  text-align: left;
  gap: 12px;
}

.card-info {
  flex: 1;
  min-width: 0;
}

.agent-name {
  font-weight: 600;
  font-size: 15px;
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-id {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-family: monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-badges {
  display: flex;
  align-items: center;
  gap: 6px;
  justify-content: center;
  flex-wrap: wrap;
  margin-top: 4px;
}

.card-body--horizontal .agent-badges {
  justify-content: flex-start;
}

.skill-level {
  font-size: 12px;
}
.star {
  color: var(--el-border-color);
}
.star.active {
  color: #f5a623;
}

.agent-capabilities {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  justify-content: center;
  margin-top: 4px;
}
.card-body--horizontal .agent-capabilities {
  justify-content: flex-start;
}
.cap-tag {
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.cap-more {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.agent-desc {
  font-size: 13px;
  color: var(--el-text-color-regular);
  margin-top: 4px;
  line-height: 1.4;
}

.agent-stats {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}

.card-actions {
  display: flex;
  gap: 6px;
  justify-content: center;
  padding-top: 8px;
  border-top: 1px solid var(--el-border-color-lighter);
  margin-top: 8px;
}

/* 移动端自动切换为横向 */
@media (max-width: 767px) {
  .card-body:not(.card-body--horizontal) {
    flex-direction: row;
    text-align: left;
    gap: 12px;
  }
  .agent-badges,
  .agent-capabilities {
    justify-content: flex-start;
  }
  .agent-desc {
    display: none;
  }
}
</style>
