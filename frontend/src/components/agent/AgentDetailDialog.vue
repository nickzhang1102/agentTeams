<template>
  <el-dialog
    v-model="visible"
    :title="displayName || 'Agent 详情'"
    width="580px"
    class="agent-detail-dialog"
  >
    <div v-if="agent" class="detail-content">
      <!-- 头部信息 -->
      <div class="detail-header">
        <AgentPortrait
          :portrait-url="agent.portrait_url"
          :agent-id="agent.agent_id"
          :name="displayName"
          :category="primaryCategory"
          :size="72"
        />
        <div class="header-info">
          <h3 class="detail-name">{{ displayName }}</h3>
          <code class="detail-id">{{ agent.agent_id }}</code>
          <div class="detail-badges">
            <el-tag v-if="agent.is_system" size="small" type="info">系统</el-tag>
            <el-tag v-else size="small" type="success">自建</el-tag>
            <el-tag v-if="!agent.is_enabled" size="small" type="warning">已禁用</el-tag>
            <el-tag v-if="agent.model && agent.model !== 'inherit'" size="small" type="info">
              {{ agent.model }}
            </el-tag>
          </div>
        </div>
      </div>

      <!-- 描述 -->
      <div v-if="agent.description" class="detail-section">
        <h4>描述</h4>
        <p>{{ agent.description }}</p>
      </div>

      <!-- 能力标签 -->
      <div v-if="agent.capabilities?.length" class="detail-section">
        <h4>能力标签</h4>
        <div class="caps-list">
          <el-tag
            v-for="cap in agent.capabilities"
            :key="cap"
            size="small"
            type="info"
            effect="plain"
          >{{ cap }}</el-tag>
        </div>
      </div>

      <!-- 统计信息 -->
      <div class="detail-section">
        <h4>统计</h4>
        <el-descriptions :column="2" size="small" border>
          <el-descriptions-item label="调用次数">{{ agent.total_calls || 0 }}</el-descriptions-item>
          <el-descriptions-item label="成功率">
            <span v-if="agent.total_calls">{{ successRate }}%</span>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item label="技能等级">
            <span class="skill-level">
              <span v-for="n in 5" :key="n" class="star" :class="{ active: n <= (agent.skill_level || 3) }">★</span>
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="分类">{{ agent.category || '-' }}</el-descriptions-item>
        </el-descriptions>
      </div>

      <!-- 标签 -->
      <div v-if="agent.tags?.length" class="detail-section">
        <h4>标签</h4>
        <div class="caps-list">
          <el-tag
            v-for="tag in agent.tags"
            :key="tag"
            size="small"
            effect="plain"
          >{{ tag }}</el-tag>
        </div>
      </div>
    </div>

    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed } from 'vue'
import AgentPortrait from '@/components/agent/AgentPortrait.vue'
import { catalogLabel } from '@/utils/catalog'

const props = defineProps({
  agent: { type: Object, default: null },
  modelValue: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue'])

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

const displayName = computed(() => catalogLabel(props.agent))

const primaryCategory = computed(() => {
  if (props.agent?.category) return props.agent.category
  const tags = props.agent?.tags || []
  if (tags.includes('medical')) return 'medical'
  if (tags.includes('finance')) return 'finance'
  if (tags.includes('business')) return 'business'
  if (!props.agent?.is_system) return 'custom'
  return 'default'
})

const successRate = computed(() => {
  const total = props.agent?.total_calls || 0
  if (!total) return 0
  return Math.round(((props.agent?.success_calls || 0) / total) * 100)
})
</script>

<style lang="scss" scoped>
.detail-content {
  max-height: 60vh;
  overflow-y: auto;
}

.detail-header {
  display: flex;
  gap: 16px;
  align-items: center;
  margin-bottom: 20px;
}

.header-info {
  flex: 1;
  min-width: 0;
}

.detail-name {
  margin: 0 0 4px;
  font-size: 18px;
  font-weight: 600;
}

.detail-id {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  font-family: monospace;
}

.detail-badges {
  display: flex;
  gap: 6px;
  margin-top: 8px;
  flex-wrap: wrap;
}

.detail-section {
  margin-bottom: 16px;

  h4 {
    margin: 0 0 8px;
    font-size: 14px;
    font-weight: 600;
    color: var(--el-text-color-regular);
  }

  p {
    margin: 0;
    font-size: 14px;
    line-height: 1.6;
    color: var(--el-text-color-primary);
  }
}

.caps-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.skill-level {
  font-size: 14px;
}
.star {
  color: var(--el-border-color);
}
.star.active {
  color: #f5a623;
}
</style>
