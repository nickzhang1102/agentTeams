<template>
  <el-dialog
    v-model="visible"
    :title="readonly ? '方案详情' : isEdit ? '编辑方案' : '新建团队方案'"
    width="620px"
    :close-on-click-modal="false"
    @close="reset"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
      <el-form-item label="方案名称" prop="name">
        <el-input v-model="form.name" :disabled="readonly" placeholder="例：医学影像分析团队" maxlength="100" />
      </el-form-item>

      <el-form-item label="描述">
        <el-input v-model="form.description" :disabled="readonly" type="textarea" :rows="2" placeholder="方案用途说明" />
      </el-form-item>

      <el-form-item label="分类">
        <el-select v-model="form.category" :disabled="readonly" style="width: 100%">
          <el-option label="自定义" value="custom" />
          <el-option label="医疗" value="medical" />
          <el-option label="商业" value="business" />
          <el-option label="研究" value="research" />
        </el-select>
      </el-form-item>

      <el-form-item label="快速模式">
        <el-switch v-model="form.skip_assessment" :disabled="readonly" />
        <span class="form-hint">跳过需求评估，直接执行</span>
      </el-form-item>

      <el-form-item label="评估阈值">
        <el-slider v-model="form.assessment_threshold" :disabled="readonly" :min="0" :max="100" :step="5" show-input />
      </el-form-item>

      <el-form-item label="Agent 选择">
        <div class="agent-picker">
          <div class="selected-agents" v-if="form.agents.length">
            <div v-for="(a, idx) in form.agents" :key="idx" class="agent-item">
              <span class="agent-item-name">{{ agentNameMap[a.agent_id] || a.agent_id }}</span>
              <el-button v-if="!readonly" size="small" type="danger" text @click="removeAgent(idx)">移除</el-button>
            </div>
          </div>
          <div v-if="!readonly" class="agent-selector-row">
            <el-select
              v-model="selectedCategory"
              placeholder="分类筛选"
              clearable
              style="width: 150px; flex-shrink: 0"
            >
              <el-option
                v-for="cat in agentCategories"
                :key="cat.key"
                :label="cat.label"
                :value="cat.key"
              />
            </el-select>
            <el-select
              v-model="selectedAgentToAdd"
              filterable
              placeholder="搜索并添加 Agent..."
              style="flex: 1; min-width: 0"
              @change="addAgent"
            >
              <el-option
                v-for="agent in filteredAgents"
                :key="agent.agent_id"
                :label="catalogLabel(agent)"
                :value="agent.agent_id"
              >
                <span>{{ catalogLabel(agent) }}</span>
                <code style="margin-left: 8px; font-size: 11px; color: #999">{{ agent.agent_id }}</code>
              </el-option>
            </el-select>
          </div>
        </div>
      </el-form-item>

      <el-form-item label="额外提示">
        <el-input
          v-model="form.system_prompt_addition"
          :disabled="readonly"
          type="textarea"
          :rows="2"
          placeholder="注入到 Agent 的额外系统提示（可选）"
          maxlength="2000"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">{{ readonly ? '关闭' : '取消' }}</el-button>
      <el-button v-if="!readonly" type="primary" :loading="saving" @click="handleSubmit">
        {{ isEdit ? '保存' : '创建' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useWorkflowTemplateStore } from '@/stores/workflowTemplate'
import api from '@/utils/api'
import { useLocaleStore } from '@/stores/locale'
import { catalogLabel } from '@/utils/catalog'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  template: { type: Object, default: null },
  readonly: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'saved'])

const store = useWorkflowTemplateStore()
const localeStore = useLocaleStore()
let loadRequestId = 0

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

const isEdit = computed(() => !!props.template?.id)

// agent_id → 中文名 映射：优先 resolved_agents，补充 allAgents 缓存
const agentNameMap = computed(() => {
  const map = {}
  // 1. resolved_agents（编辑时模板自带）
  const resolved = props.template?.resolved_agents || []
  for (const a of resolved) {
    if (a.agent_id && catalogLabel(a)) map[a.agent_id] = catalogLabel(a)
  }
  // 2. 已加载的完整 Agent 列表（包含新添加的 agent）
  for (const a of allAgents.value) {
    if (a.agent_id && catalogLabel(a) && !map[a.agent_id]) map[a.agent_id] = catalogLabel(a)
  }
  return map
})

const formRef = ref(null)
const saving = ref(false)
const selectedAgentToAdd = ref(null)
const selectedCategory = ref(null)
const allAgents = ref([])
const categoryMeta = ref({}) // key → {name, icon}

// 从已加载的 Agent 列表动态提取分类，名称从 API 获取
const agentCategories = computed(() => {
  const map = new Map()
  for (const a of allAgents.value) {
    const key = a.category || 'default'
    if (!map.has(key)) map.set(key, 0)
    map.set(key, map.get(key) + 1)
  }
  return [...map.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([key, count]) => ({
      key,
      label: `${categoryMeta.value[key]?.label || key} (${count})`,
    }))
})

const availableAgents = computed(() => {
  const selectedIds = new Set(form.value.agents.map(a => a.agent_id))
  return allAgents.value.filter(a => !selectedIds.has(a.agent_id) && a.is_enabled)
})

const filteredAgents = computed(() => {
  if (!selectedCategory.value) return availableAgents.value
  return availableAgents.value.filter(a => (a.category || 'default') === selectedCategory.value)
})

const defaultForm = () => ({
  name: '',
  description: '',
  category: 'custom',
  agents: [],
  skip_assessment: false,
  assessment_threshold: 60,
  system_prompt_addition: '',
})

const form = ref(defaultForm())

const rules = {
  name: [{ required: true, message: '请输入方案名称', trigger: 'blur' }],
}

watch(visible, async (val) => {
  if (val) {
    selectedCategory.value = null
    await loadAgents()
    if (props.template) {
      // 优先用 resolved_agents（含 pack 解析出的 agents + 中文名）
      const agentSource = props.template.resolved_agents?.length
        ? props.template.resolved_agents
        : (props.template.agents || [])
      form.value = {
        name: props.template.name || '',
        description: props.template.description || '',
        category: props.template.category || 'custom',
        agents: agentSource.map(a => ({ ...a })),
        skip_assessment: props.template.skip_assessment || false,
        assessment_threshold: props.template.assessment_threshold ?? 60,
        system_prompt_addition: props.template.system_prompt_addition || '',
      }
    } else {
      form.value = defaultForm()
    }
  }
})

watch(() => localeStore.locale, () => {
  if (visible.value) loadAgents()
})

async function loadAgents() {
  const requestId = ++loadRequestId
  const requestLocale = localeStore.locale
  try {
    const [agentsRes, catsRes] = await Promise.all([
      api.get('/api/agents', { params: { locale: requestLocale } }),
      api.get('/api/agents/categories', { params: { locale: requestLocale } }),
    ])
    if (requestId !== loadRequestId) return
    allAgents.value = agentsRes.data.agents || []
    const cats = catsRes.data.categories || []
    categoryMeta.value = Object.fromEntries(
      cats.filter(c => c.key !== 'all').map(c => [c.key, { label: catalogLabel(c), icon: c.icon }])
    )
  } catch {
    if (requestId === loadRequestId) allAgents.value = []
  }
}

function addAgent(agentId) {
  if (!agentId) return
  form.value.agents.push({
    agent_id: agentId,
    order: form.value.agents.length + 1,
  })
  selectedAgentToAdd.value = null
}

function removeAgent(idx) {
  form.value.agents.splice(idx, 1)
}

function reset() {
  form.value = defaultForm()
  formRef.value?.resetFields()
}

async function handleSubmit() {
  try {
    await formRef.value.validate()
  } catch { return }

  saving.value = true
  const data = { ...form.value }
  if (data.agents.length === 0) data.agents = null

  const result = isEdit.value
    ? await store.updateTemplate(props.template.id, data)
    : await store.createTemplate(data)

  saving.value = false

  if (result.success) {
    ElMessage.success(isEdit.value ? '已更新' : '已创建')
    emit('saved', result.template)
  } else {
    ElMessage.error(result.error)
  }
}
</script>

<style lang="scss" scoped>
.form-hint {
  margin-left: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.agent-picker {
  width: 100%;
}

.selected-agents {
  margin-bottom: 8px;
}

.agent-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}

.agent-item-name {
  font-size: 13px;
  font-weight: 500;
  min-width: 100px;
}

.agent-selector-row {
  display: flex;
  gap: 8px;
}
</style>
