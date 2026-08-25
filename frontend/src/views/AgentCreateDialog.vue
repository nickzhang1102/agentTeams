<template>
  <el-dialog
    :model-value="modelValue"
    :title="isEdit ? '编辑 Agent' : '新建 Agent'"
    width="600px"
    @close="$emit('update:modelValue', false)"
  >
    <el-form :model="form" label-position="top" :rules="rules" ref="formRef">
      <el-form-item label="Agent ID" prop="agent_id" v-if="!isEdit">
        <el-input v-model="form.agent_id" placeholder="my-custom-agent" :disabled="isEdit" />
        <div class="form-hint">小写字母、数字、连字符，3-50 字符</div>
      </el-form-item>

      <el-form-item label="名称" prop="name">
        <el-input v-model="form.name" placeholder="我的分析师" />
      </el-form-item>

      <el-form-item label="描述">
        <el-input v-model="form.description" type="textarea" :rows="2" placeholder="Agent 功能描述" />
      </el-form-item>

      <el-form-item label="模型">
        <el-select v-model="form.model" style="width: 100%">
          <el-option
            v-for="m in availableModels"
            :key="m.id"
            :label="m.name"
            :value="m.id"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="角色">
        <el-input v-model="form.role" placeholder="一句话角色描述" maxlength="200" />
      </el-form-item>

      <el-form-item label="专业度">
        <el-slider v-model="form.skill_level" :min="1" :max="5" :step="1" show-stops />
      </el-form-item>

      <el-form-item label="能力标签">
        <div class="tags-input">
          <el-tag
            v-for="(cap, idx) in form.capabilities"
            :key="idx"
            closable
            @close="form.capabilities.splice(idx, 1)"
          >{{ cap }}</el-tag>
          <el-input
            v-if="capInputVisible"
            ref="capInputRef"
            v-model="capInputValue"
            size="small"
            style="width: 120px"
            @keyup.enter="addCapability"
            @blur="addCapability"
          />
          <el-button v-else size="small" @click="showCapInput">+ 添加</el-button>
        </div>
      </el-form-item>

      <el-form-item label="业务标签">
        <div class="tags-input">
          <el-tag
            v-for="(tag, idx) in form.tags"
            :key="idx"
            closable
            type="info"
            @close="form.tags.splice(idx, 1)"
          >{{ tag }}</el-tag>
          <el-input
            v-if="tagInputVisible"
            ref="tagInputRef"
            v-model="tagInputValue"
            size="small"
            style="width: 120px"
            @keyup.enter="addTag"
            @blur="addTag"
          />
          <el-button v-else size="small" @click="showTagInput">+ 添加</el-button>
        </div>
      </el-form-item>

      <el-form-item label="System Prompt" prop="content">
        <div class="content-header">
          <el-tooltip content="AI 生成即将上线，敬请期待" placement="top">
            <el-button type="primary" link disabled>
              🤖 AI 生成
            </el-button>
          </el-tooltip>
        </div>
        <el-input
          v-model="form.content"
          type="textarea"
          :rows="10"
          placeholder="Agent 的 system prompt 内容（Markdown 格式）"
          class="code-textarea"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" @click="handleSave" :loading="saving">
        {{ isEdit ? '保存' : '创建' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { useAgentsStore } from '@/stores/agents'
import api from '@/utils/api'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  editAgent: { type: Object, default: null },
})
const emit = defineEmits(['update:modelValue', 'saved'])

const store = useAgentsStore()
const formRef = ref(null)
const saving = ref(false)

const isEdit = computed(() => !!props.editAgent)

// 动态模型列表
const availableModels = ref([{ id: 'inherit', name: '继承默认 (inherit)' }])
async function fetchModels() {
  try {
    const res = await api.get('/api/agents/models')
    const models = (res.data.models || []).map(m => ({
      id: m.id,
      name: m.name || m.id,
    }))
    availableModels.value = [{ id: 'inherit', name: '继承默认 (inherit)' }, ...models]
  } catch { /* fallback to default */ }
}

const defaultForm = () => ({
  agent_id: '',
  name: '',
  description: '',
  model: 'inherit',
  role: '',
  skill_level: 3,
  capabilities: [],
  tags: [],
  content: '',
})

const form = ref(defaultForm())

const rules = {
  agent_id: [
    { required: true, message: '请输入 Agent ID', trigger: 'blur' },
    { pattern: /^[a-zA-Z0-9\-]+$/, message: '只能包含字母、数字、连字符', trigger: 'blur' },
    { min: 3, max: 50, message: '3-50 个字符', trigger: 'blur' },
  ],
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  content: [{ required: true, message: '请输入 System Prompt', trigger: 'blur' }],
}

// 标签输入
const capInputVisible = ref(false)
const capInputValue = ref('')
const capInputRef = ref(null)

const tagInputVisible = ref(false)
const tagInputValue = ref('')
const tagInputRef = ref(null)

function showCapInput() {
  capInputVisible.value = true
  nextTick(() => capInputRef.value?.focus())
}
function addCapability() {
  if (capInputValue.value.trim()) {
    form.value.capabilities.push(capInputValue.value.trim())
  }
  capInputVisible.value = false
  capInputValue.value = ''
}

function showTagInput() {
  tagInputVisible.value = true
  nextTick(() => tagInputRef.value?.focus())
}
function addTag() {
  if (tagInputValue.value.trim()) {
    form.value.tags.push(tagInputValue.value.trim())
  }
  tagInputVisible.value = false
  tagInputValue.value = ''
}

// 打开弹窗时初始化表单
watch(() => props.modelValue, (val) => {
  if (val) {
    fetchModels()  // 动态加载模型列表
    if (props.editAgent) {
      form.value = {
        agent_id: props.editAgent.agent_id,
        name: props.editAgent.name || '',
        description: props.editAgent.description || '',
        model: props.editAgent.model || 'inherit',
        role: props.editAgent.role || '',
        skill_level: props.editAgent.skill_level || 3,
        capabilities: [...(props.editAgent.capabilities || [])],
        tags: [...(props.editAgent.tags || [])],
        content: props.editAgent.content || '',
      }
    } else {
      form.value = defaultForm()
    }
  }
})

async function handleSave() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }

  saving.value = true
  let result
  if (isEdit.value) {
    result = await store.updateUserAgent(form.value.agent_id, form.value)
  } else {
    result = await store.createUserAgent(form.value)
  }
  saving.value = false

  if (result.success) {
    ElMessage.success(isEdit.value ? '已保存' : '已创建（等待管理员审核）')
    emit('saved')
  } else {
    ElMessage.error(result.error)
  }
}
</script>

<style scoped>
.form-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}
.tags-input {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.content-header {
  margin-bottom: 8px;
}
.code-textarea :deep(textarea) {
  font-family: 'Courier New', monospace;
  font-size: 13px;
}
</style>
