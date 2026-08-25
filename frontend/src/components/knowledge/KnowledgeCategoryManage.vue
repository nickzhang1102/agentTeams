<template>
  <div class="category-manage">
    <!-- 分类列表 -->
    <el-table
      :data="categories"
      v-loading="loading"
      :empty-text="t('knowledge.categories.empty')"
      class="category-table"
    >
      <el-table-column :label="t('knowledge.categories.sort')" prop="sort_order" width="90">
        <template #default="{ row, $index }">
          <div class="sort-cell">
            <button
              class="sort-btn"
              :disabled="$index === 0"
              @click="moveUp($index)"
              :title="t('knowledge.categories.moveUp')"
            >
              <el-icon><Top /></el-icon>
            </button>
            <span class="sort-num">{{ $index + 1 }}</span>
            <button
              class="sort-btn"
              :disabled="$index === categories.length - 1"
              @click="moveDown($index)"
              :title="t('knowledge.categories.moveDown')"
            >
              <el-icon><Bottom /></el-icon>
            </button>
          </div>
        </template>
      </el-table-column>

      <el-table-column :label="t('knowledge.categories.key')" prop="key" width="120" />

      <el-table-column :label="t('knowledge.categories.displayName')" prop="label" width="120" />

      <el-table-column :label="t('knowledge.categories.description')" prop="description" min-width="150">
        <template #default="{ row }">
          {{ row.description || '-' }}
        </template>
      </el-table-column>

      <el-table-column :label="t('knowledge.categories.icon')" prop="icon" width="120">
        <template #default="{ row }">
          <div class="icon-preview">
            <el-icon class="icon-preview-el"><component :is="iconMap[row.icon] || Document" /></el-icon>
            <span>{{ row.icon }}</span>
          </div>
        </template>
      </el-table-column>

      <el-table-column :label="t('knowledge.categories.active')" prop="is_active" width="80">
        <template #default="{ row }">
          <el-switch
            v-model="row.is_active"
            @change="handleActiveChange(row)"
          />
        </template>
      </el-table-column>

      <el-table-column :label="t('knowledge.documents.operations')" width="150" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" size="small" text @click="showEditDialog(row)">
            {{ t('knowledge.categories.edit') }}
          </el-button>
          <el-button type="danger" size="small" text @click="handleDelete(row)">
            {{ t('knowledge.actions.delete') }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>

  <!-- 新增/编辑弹窗 -->
  <el-dialog
    v-model="dialogVisible"
    :title="isEdit ? t('knowledge.categories.editTitle') : t('knowledge.categories.createTitle')"
    width="400px"
    :close-on-click-modal="false"
  >
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="80px"
    >
      <el-form-item :label="t('knowledge.categories.key')" prop="key">
        <el-input
          v-model="form.key"
          :placeholder="t('knowledge.categories.keyPlaceholder')"
          :disabled="isEdit"
        />
      </el-form-item>
      <el-form-item :label="t('knowledge.categories.displayName')" prop="label">
        <el-input v-model="form.label" :placeholder="t('knowledge.categories.labelPlaceholder')" />
      </el-form-item>
      <el-form-item :label="t('knowledge.categories.description')" prop="description">
        <el-input v-model="form.description" :placeholder="t('knowledge.categories.descriptionPlaceholder')" />
      </el-form-item>
      <el-form-item :label="t('knowledge.categories.icon')" prop="icon">
        <el-select v-model="form.icon" :placeholder="t('knowledge.categories.iconPlaceholder')" style="width: 100%">
          <el-option
            v-for="opt in iconOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          >
            <div class="icon-option">
              <el-icon><component :is="opt.component" /></el-icon>
              <span>{{ opt.label }}</span>
            </div>
          </el-option>
        </el-select>
      </el-form-item>
      <el-form-item :label="t('knowledge.categories.enabled')" prop="is_active">
        <el-switch v-model="form.is_active" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">{{ t('knowledge.actions.cancel') }}</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit">
        {{ t('knowledge.actions.confirm') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus, Top, Bottom, Document, Folder, Reading, Collection,
  DataLine, Setting, Management, PriceTag, Memo, Files,
  Notebook, EditPen, Calendar, Star, TrophyBase
} from '@element-plus/icons-vue'
import { useKnowledgeStore } from '@/stores/knowledge'

const knowledgeStore = useKnowledgeStore()
const { t } = useI18n()

// 图标名称 → 组件映射（表格预览用）
const iconMap = {
  Document, Folder, Reading, Collection, DataLine,
  Setting, Management, PriceTag, Memo, Files,
  Notebook, EditPen, Calendar, Star, TrophyBase
}

// 图标选项（选择器用）
const iconOptionDefs = [
  { value: 'Document', component: Document },
  { value: 'Folder', component: Folder },
  { value: 'Reading', component: Reading },
  { value: 'Collection', component: Collection },
  { value: 'Files', component: Files },
  { value: 'Notebook', component: Notebook },
  { value: 'Memo', component: Memo },
  { value: 'EditPen', component: EditPen },
  { value: 'DataLine', component: DataLine },
  { value: 'PriceTag', component: PriceTag },
  { value: 'Star', component: Star },
  { value: 'TrophyBase', component: TrophyBase },
  { value: 'Setting', component: Setting },
  { value: 'Management', component: Management },
  { value: 'Calendar', component: Calendar },
]

const iconOptions = computed(() => iconOptionDefs.map((option) => ({
  ...option,
  label: t(`knowledge.categories.icons.${option.value}`)
})))

// 状态
const loading = ref(false)
const dialogVisible = ref(false)
const isEdit = ref(false)
const submitting = ref(false)
const editId = ref(null)

// 分类列表
const categories = ref([])

// 表单
const formRef = ref(null)
const form = ref({
  key: '',
  label: '',
  description: '',
  icon: 'Folder',
  is_active: true
})

// 校验规则
const rules = computed(() => ({
  key: [
    { required: true, message: t('knowledge.categories.keyRequired'), trigger: 'blur' },
    { pattern: /^[a-z][a-z0-9_]*$/, message: t('knowledge.categories.keyPattern'), trigger: 'blur' }
  ],
  label: [
    { required: true, message: t('knowledge.categories.labelRequired'), trigger: 'blur' }
  ]
}))

// 加载分类列表
async function fetchCategories() {
  loading.value = true
  try {
    const result = await knowledgeStore.fetchAdminCategories()
    if (result.success) {
      categories.value = result.categories
    } else {
      ElMessage.error(result.error || t('knowledge.categories.fetchFailed'))
    }
  } finally {
    loading.value = false
  }
}

// 新增弹窗
function showCreateDialog() {
  isEdit.value = false
  editId.value = null
  form.value = {
    key: '',
    label: '',
    description: '',
    icon: 'Folder',
    is_active: true
  }
  dialogVisible.value = true
}

// 暴露给父组件调用
defineExpose({ showCreateDialog })

// 编辑弹窗
function showEditDialog(row) {
  isEdit.value = true
  editId.value = row.id
  form.value = {
    key: row.key,
    label: row.name || row.label,
    description: row.description || '',
    icon: row.icon,
    is_active: row.is_active
  }
  dialogVisible.value = true
}

// 提交
async function handleSubmit() {
  if (!formRef.value) return

  try {
    await formRef.value.validate()
  } catch {
    return
  }

  submitting.value = true

  try {
    let result
    if (isEdit.value) {
      result = await knowledgeStore.updateCategory(editId.value, {
        label: form.value.label,
        description: form.value.description,
        icon: form.value.icon,
        is_active: form.value.is_active
      })
    } else {
      // 新增：排序自动追加到末尾
      const maxOrder = categories.value.length > 0
        ? Math.max(...categories.value.map(c => c.sort_order))
        : -1
      result = await knowledgeStore.createCategory({
        key: form.value.key,
        label: form.value.label,
        description: form.value.description,
        icon: form.value.icon,
        sort_order: maxOrder + 1,
        is_active: form.value.is_active
      })
    }

    if (result.success) {
      ElMessage.success(isEdit.value ? t('knowledge.categories.updated') : t('knowledge.categories.created'))
      dialogVisible.value = false
      await fetchCategories()
    } else {
      ElMessage.error(result.error || t('knowledge.categories.operationFailed'))
    }
  } finally {
    submitting.value = false
  }
}

// 上移：本地数组交换位置 → 批量持久化
async function moveUp(index) {
  if (index <= 0) return
  const list = [...categories.value]
  const a = list[index - 1]
  const b = list[index]
  // 交换 sort_order
  const tmp = a.sort_order
  a.sort_order = b.sort_order
  b.sort_order = tmp
  // 本地立即生效
  list[index - 1] = b
  list[index] = a
  categories.value = list
  // 持久化
  await persistSort(a, b)
}

// 下移
async function moveDown(index) {
  if (index >= categories.value.length - 1) return
  const list = [...categories.value]
  const a = list[index]
  const b = list[index + 1]
  const tmp = a.sort_order
  a.sort_order = b.sort_order
  b.sort_order = tmp
  list[index] = b
  list[index + 1] = a
  categories.value = list
  await persistSort(a, b)
}

// 批量保存排序
async function persistSort(a, b) {
  try {
    const [r1, r2] = await Promise.all([
      knowledgeStore.updateCategory(a.id, { sort_order: a.sort_order }),
      knowledgeStore.updateCategory(b.id, { sort_order: b.sort_order })
    ])
    if (!r1.success || !r2.success) {
      ElMessage.error(t('knowledge.categories.sortFailedRestored'))
      await fetchCategories()
    }
  } catch {
    ElMessage.error(t('knowledge.categories.sortFailed'))
    await fetchCategories()
  }
}

// 启用状态变更
async function handleActiveChange(row) {
  try {
    const result = await knowledgeStore.updateCategory(row.id, { is_active: row.is_active })
    if (result.success) {
      ElMessage.success(row.is_active ? t('knowledge.categories.enabledMessage') : t('knowledge.categories.disabledMessage'))
      await fetchCategories()
    } else {
      ElMessage.error(result.error || t('knowledge.categories.updateFailed'))
      row.is_active = !row.is_active
    }
  } catch {
    ElMessage.error(t('knowledge.categories.updateFailed'))
    row.is_active = !row.is_active
  }
}

// 删除
async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(
      t('knowledge.categories.deleteMessage', { name: row.name || row.label }),
      t('knowledge.categories.deleteTitle'),
      {
        confirmButtonText: t('knowledge.actions.confirmDelete'),
        cancelButtonText: t('knowledge.actions.cancel'),
        type: 'warning'
      }
    )

    const result = await knowledgeStore.deleteCategory(row.id)
    if (result.success) {
      ElMessage.success(t('knowledge.categories.deleted'))
      await fetchCategories()
    } else {
      ElMessage.error(result.error || t('knowledge.categories.deleteFailed'))
    }
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error(t('knowledge.categories.deleteFailed'))
    }
  }
}

// 初始化
onMounted(() => {
  fetchCategories()
})
</script>

<style scoped lang="scss">
.category-manage {
  /* 无额外包装，由父级 tabs-container 提供卡片容器 */
}

/* 排序控件 */
.sort-cell {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.sort-num {
  display: inline-block;
  min-width: 16px;
  text-align: center;
  font-size: var(--font-size-xs);
  font-weight: 600;
  color: var(--color-text);
}

.sort-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  min-height: 0 !important;  /* 覆盖全局 button min-height: 44px */
  min-width: 0 !important;
  padding: 0;
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  color: #CBD5E1;
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-in-out);

  &:hover:not(:disabled) {
    color: var(--color-primary);
    border-color: var(--color-primary);
    background: rgba(37, 99, 235, 0.04);
  }

  &:disabled {
    opacity: 0.25;
    cursor: not-allowed;
  }

  .el-icon {
    font-size: 11px;
  }
}

/* 图标预览（表格内） */
.icon-preview {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--font-size-xs);
  color: #64748B;
}

.icon-preview-el {
  font-size: 16px;
  color: var(--color-primary);
}

/* 图标选择器选项 */
.icon-option {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 表格 — 与文档列表一致：无边框，干净融入 */
.category-table {
  :deep(.el-table__inner-wrapper) {
    &::before {
      display: none;
    }
  }

  :deep(.el-table__border-left-patch) {
    display: none;
  }

  :deep(.el-table__header th) {
    background: transparent;
    font-weight: 600;
    color: #475569;
    font-size: var(--font-size-sm);
    border-bottom: 1px solid var(--color-border) !important;
  }

  :deep(.el-table__row) {
    transition: background var(--duration-fast) var(--ease-in-out);

    &:hover {
      background: #F8FAFC !important;
    }

    td {
      border-bottom: none !important;
    }
  }

  :deep(.el-table__cell) {
    padding: 10px 0;
  }

  :deep(.el-button) {
    transition: all var(--duration-fast) var(--ease-in-out);

    &:hover {
      transform: translateY(-1px);
    }
  }
}
</style>
