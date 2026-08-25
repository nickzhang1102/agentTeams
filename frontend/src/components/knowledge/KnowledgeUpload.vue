<template>
  <el-dialog
    v-model="visible"
    :title="t('knowledge.upload.title')"
    width="500px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="80px"
    >
      <!-- 分类选择（动态渲染） -->
      <el-form-item :label="t('knowledge.upload.category')" prop="category">
        <el-select
          v-model="form.category"
          :placeholder="t('knowledge.upload.categoryPlaceholder')"
          style="width: 100%"
        >
          <el-option
            v-for="cat in categories"
            :key="cat.key"
            :label="cat.label"
            :value="cat.key"
          />
        </el-select>
      </el-form-item>

      <!-- 文件上传 -->
      <el-form-item :label="t('knowledge.upload.file')" prop="file">
        <el-upload
          ref="uploadRef"
          :auto-upload="false"
          :limit="1"
          :on-change="handleFileChange"
          :on-exceed="handleExceed"
          :file-list="fileList"
          drag
          class="upload-area"
        >
          <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
          <div class="el-upload__text">
            {{ t('knowledge.upload.dragText') }} <em>{{ t('knowledge.upload.clickSelect') }}</em>
          </div>
          <template #tip>
            <div class="el-upload__tip">
              {{ t('knowledge.upload.tip') }}
            </div>
          </template>
        </el-upload>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="handleClose">{{ t('knowledge.actions.cancel') }}</el-button>
      <el-button
        type="primary"
        :loading="uploading"
        :disabled="!form.file"
        @click="handleUpload"
      >
        {{ t('knowledge.upload.submit') }}
      </el-button>
    </template>
  </el-dialog>

  <!-- 去重选择弹窗 -->
  <el-dialog
    v-model="duplicateDialogVisible"
    :title="t('knowledge.upload.duplicateTitle')"
    width="400px"
    :close-on-click-modal="false"
  >
    <div class="duplicate-content">
      <el-icon :size="48" color="#E6A23C"><Warning /></el-icon>
      <p class="duplicate-message">{{ t('knowledge.upload.duplicateMessage') }}</p>
      <p class="duplicate-info">{{ t('knowledge.upload.duplicateDocument', { filename: duplicateDocFilename }) }}</p>
    </div>
    <template #footer>
      <div class="duplicate-footer">
        <el-button @click="handleDuplicateCancel">{{ t('knowledge.upload.cancelUpload') }}</el-button>
        <el-button @click="handleDuplicateKeepBoth">{{ t('knowledge.upload.keepBoth') }}</el-button>
        <el-button type="warning" @click="handleDuplicateOverwrite">
          {{ t('knowledge.upload.overwrite') }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { UploadFilled, Warning } from '@element-plus/icons-vue'
import { useKnowledgeStore } from '@/stores/knowledge'

// Props
const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  }
})

// Emits
const emit = defineEmits(['close', 'success'])

// Store
const knowledgeStore = useKnowledgeStore()
const { t } = useI18n()

// 状态
const formRef = ref(null)
const uploadRef = ref(null)
const uploading = ref(false)
const fileList = ref([])
const duplicateDialogVisible = ref(false)
const duplicateDocId = ref(null)
const duplicateDocFilename = ref('')
const pendingFile = ref(null)
const pendingCategory = ref('')

// 表单
const form = ref({
  category: '',
  file: null
})

// 校验规则
const rules = computed(() => ({
  category: [
    { required: true, message: t('knowledge.upload.categoryRequired'), trigger: 'change' }
  ],
  file: [
    { required: true, message: t('knowledge.upload.fileRequired'), trigger: 'change' }
  ]
}))

// 计算属性
const visible = computed({
  get: () => props.visible,
  set: (val) => {
    if (!val) {
      emit('close')
    }
  }
})

// 分类列表（从 store 获取）
const categories = computed(() => knowledgeStore.categories)

// 文件类型白名单（与后端 upload_validator 对齐）
const ALLOWED_EXTENSIONS = [
  '.pdf', '.docx', '.doc', '.md', '.txt',
  '.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'
]
const MAX_FILE_SIZE = 10 * 1024 * 1024  // 10MB

// 弹窗打开时加载分类列表
watch(() => props.visible, async (val) => {
  if (val && knowledgeStore.categories.length === 0) {
    await knowledgeStore.fetchCategories()
  }
})

// 方法
function handleFileChange(file) {
  // 校验文件类型
  const ext = '.' + file.name.split('.').pop().toLowerCase()
  if (!ALLOWED_EXTENSIONS.includes(ext)) {
    ElMessage.error(t('knowledge.upload.unsupportedType', { ext }))
    fileList.value = []
    form.value.file = null
    return
  }

  // 校验文件大小
  if (file.size > MAX_FILE_SIZE) {
    ElMessage.error(t('knowledge.upload.tooLarge'))
    fileList.value = []
    form.value.file = null
    return
  }

  // 文件有效
  form.value.file = file.raw
  fileList.value = [file]
}

function handleExceed(files) {
  // 超出 limit 时替换
  fileList.value = []
  form.value.file = null
  handleFileChange(files[0])
}

function handleClose() {
  // 重置表单
  form.value = { category: '', file: null }
  fileList.value = []
  duplicateDialogVisible.value = false
  pendingFile.value = null
  pendingCategory.value = ''
  emit('close')
}

async function handleUpload() {
  if (!formRef.value) return

  // 表单校验
  try {
    await formRef.value.validate()
  } catch {
    return
  }

  if (!form.value.file) {
    ElMessage.warning(t('knowledge.upload.selectFile'))
    return
  }

  uploading.value = true

  try {
    const result = await knowledgeStore.uploadDocument(
      form.value.file,
      form.value.category
    )

    if (result.success) {
      ElMessage.success(result.document?.message || t('knowledge.upload.success'))
      emit('success', result.document)
      handleClose()
    } else if (result.error_code === 'duplicate') {
      // 显示去重弹窗
      duplicateDocId.value = result.duplicate_doc_id
      duplicateDocFilename.value = await fetchDocFilename(result.duplicate_doc_id)
      pendingFile.value = form.value.file
      pendingCategory.value = form.value.category
      duplicateDialogVisible.value = true
    } else {
      ElMessage.error(result.error || t('knowledge.upload.failed'))
    }
  } catch (error) {
    ElMessage.error(t('knowledge.upload.retry'))
  } finally {
    uploading.value = false
  }
}

// 获取重复文档文件名
async function fetchDocFilename(docId) {
  try {
    const doc = knowledgeStore.documents.find(d => d.id === docId)
    if (doc) {
      return doc.filename
    }
    // 刷新列表获取文档信息
    await knowledgeStore.fetchDocuments()
    const found = knowledgeStore.documents.find(d => d.id === docId)
    return found?.filename || t('knowledge.upload.duplicateFallback', { id: docId })
  } catch {
    return t('knowledge.upload.duplicateFallback', { id: docId })
  }
}

// 去重处理
async function handleDuplicateCancel() {
  // 取消上传
  duplicateDialogVisible.value = false
  duplicateDocId.value = null
  pendingFile.value = null
  pendingCategory.value = null
  ElMessage.info(t('knowledge.upload.cancelled'))
}

async function handleDuplicateKeepBoth() {
  // 保留两者：带 allow_duplicate=true 重传
  duplicateDialogVisible.value = false
  uploading.value = true

  try {
    const result = await knowledgeStore.uploadDocument(
      pendingFile.value,
      pendingCategory.value,
      { allow_duplicate: true }
    )

    if (result.success) {
      ElMessage.success(t('knowledge.upload.success'))
      emit('success', result.document)
      handleClose()
    } else {
      ElMessage.error(result.error || t('knowledge.upload.failed'))
    }
  } catch (error) {
    ElMessage.error(t('knowledge.upload.retry'))
  } finally {
    uploading.value = false
    pendingFile.value = null
    pendingCategory.value = null
  }
}

async function handleDuplicateOverwrite() {
  // 覆盖旧文档：先删除旧文档，再重传
  duplicateDialogVisible.value = false
  uploading.value = true

  try {
    // 删除旧文档
    await knowledgeStore.deleteDocument(duplicateDocId.value)

    // 重传新文档
    const result = await knowledgeStore.uploadDocument(
      pendingFile.value,
      pendingCategory.value
    )

    if (result.success) {
      ElMessage.success(t('knowledge.upload.overwriteSuccess'))
      emit('success', result.document)
      handleClose()
    } else {
      ElMessage.error(result.error || t('knowledge.upload.failed'))
    }
  } catch (error) {
    ElMessage.error(t('knowledge.upload.operationFailed'))
  } finally {
    uploading.value = false
    pendingFile.value = null
    pendingCategory.value = null
    duplicateDocId.value = null
  }
}
</script>

<style scoped lang="scss">
.upload-area {
  width: 100%;

  :deep(.el-upload-dragger) {
    width: 100%;
  }
}

.duplicate-content {
  text-align: center;
  padding: 20px 0;

  .duplicate-message {
    font-size: 16px;
    color: var(--color-text);
    margin: 16px 0 8px;
  }

  .duplicate-info {
    font-size: 14px;
    color: #909399;
  }
}

.duplicate-footer {
  display: flex;
  justify-content: center;
  gap: 12px;
}
</style>
