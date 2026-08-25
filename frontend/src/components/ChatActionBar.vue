<template>
  <div class="chat-action-bar">
    <el-button-group>
      <el-button
        size="small"
        circle
        :icon="DocumentCopy"
        @click="handleCopy"
        :title="t('leader.actions.copy')"
      />
      <el-button
        size="small"
        circle
        :icon="Download"
        :loading="isGeneratingPDF"
        @click="handleDownloadPDF"
        :title="t('leader.actions.downloadPdf')"
      />
      <el-button
        size="small"
        circle
        :icon="Picture"
        :loading="isGeneratingImage"
        @click="handleDownloadImage"
        :title="t('leader.actions.downloadImage')"
      />
    </el-button-group>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { DocumentCopy, Download, Picture } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const { t, locale } = useI18n()

const props = defineProps({
  message: {
    type: Object,
    required: true
  },
  conversationId: {
    type: [String, Number],
    required: true
  }
})

const isGeneratingPDF = ref(false)
const isGeneratingImage = ref(false)

let html2pdfModulePromise = null
let html2canvasModulePromise = null

function loadHtml2pdf() {
  if (!html2pdfModulePromise) {
    html2pdfModulePromise = import('html2pdf.js').then((mod) => mod.default)
  }
  return html2pdfModulePromise
}

function loadHtml2canvas() {
  if (!html2canvasModulePromise) {
    html2canvasModulePromise = import('html2canvas').then((mod) => mod.default)
  }
  return html2canvasModulePromise
}

async function handleCopy() {
  try {
    const content = formatConversation(props.message)

    // 优先使用现代剪贴板 API
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(content)
      ElMessage.success(t('leader.actions.copied'))
      return
    }

    // 降级方案：使用传统的复制方法
    const textArea = document.createElement('textarea')
    textArea.value = content

    // 防止页面滚动
    textArea.style.position = 'fixed'
    textArea.style.left = '-999999px'
    textArea.style.top = '-999999px'

    document.body.appendChild(textArea)
    textArea.focus()
    textArea.select()

    try {
      const successful = document.execCommand('copy')
      document.body.removeChild(textArea)

      if (successful) {
        ElMessage.success(t('leader.actions.copied'))
      } else {
        throw new Error('COPY_COMMAND_FAILED')
      }
    } catch (err) {
      document.body.removeChild(textArea)
      throw err
    }
  } catch (error) {
    console.error('复制失败:', error)

    // 提供更详细的错误信息
    let errorMessage = t('leader.actions.copyFailed')
    if (error.name === 'NotAllowedError') {
      errorMessage = t('leader.actions.clipboardDenied')
    } else if (!window.isSecureContext) {
      errorMessage = t('leader.actions.httpsRequired')
    }

    ElMessage.error(errorMessage)
  }
}

function formatConversation(message) {
  const timestamp = new Date().toLocaleString(locale.value)
  const userContent = message.user_content || '...'
  const assistantContent = message.content || message.response || '...'

  return `
 ${assistantContent}
`
}

async function handleDownloadPDF() {
  if (isGeneratingPDF.value) return

  if (!props.message.id) {
    ElMessage.error(t('leader.actions.missingPdfId'))
    return
  }

  const messageElement = document.querySelector(`[data-message-id="${props.message.id}"]`)
  if (!messageElement) {
    ElMessage.error(t('leader.actions.missingPdfContent'))
    console.error('未找到消息元素:', `[data-message-id="${props.message.id}"]`)
    return
  }

  isGeneratingPDF.value = true

  try {
    const html2pdf = await loadHtml2pdf()
    const opt = {
      margin: 10,
      filename: `${t('leader.actions.filename', { id: props.conversationId, timestamp: Date.now() })}.pdf`,
      image: { type: 'jpeg', quality: 0.98 },
      html2canvas: {
        scale: 2,
        useCORS: true,
        backgroundColor: '#ffffff'
      },
      jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' }
    }

    await html2pdf().set(opt).from(messageElement).save()
    ElMessage.success(t('leader.actions.pdfSuccess'))
  } catch (error) {
    console.error('PDF 生成失败:', error)
    ElMessage.error(t('leader.actions.pdfFailed'))
  } finally {
    isGeneratingPDF.value = false
  }
}

async function handleDownloadImage() {
  if (isGeneratingImage.value) return

  if (!props.message.id) {
    ElMessage.error(t('leader.actions.missingImageId'))
    return
  }

  const messageElement = document.querySelector(`[data-message-id="${props.message.id}"]`)
  if (!messageElement) {
    ElMessage.error(t('leader.actions.missingImageContent'))
    console.error('未找到消息元素:', `[data-message-id="${props.message.id}"]`)
    return
  }

  isGeneratingImage.value = true

  try {
    const html2canvas = await loadHtml2canvas()
    const canvas = await html2canvas(messageElement, {
      scale: 2,
      backgroundColor: '#ffffff',
      useCORS: true
    })

    const link = document.createElement('a')
    link.download = `${t('leader.actions.filename', { id: props.conversationId, timestamp: Date.now() })}.png`
    link.href = canvas.toDataURL('image/png')
    link.click()

    ElMessage.success(t('leader.actions.imageSuccess'))
  } catch (error) {
    console.error('图片生成失败:', error)
    ElMessage.error(t('leader.actions.imageFailed'))
  } finally {
    isGeneratingImage.value = false
  }
}
</script>

<style scoped>
.chat-action-bar {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid rgba(37, 99, 235, 0.1);
}

.chat-action-bar .el-button {
  color: #909399;
  background: transparent;
  border-color: #dcdfe6;
}

.chat-action-bar .el-button:hover {
  color: #409eff;
  background-color: rgba(64, 158, 255, 0.1);
  border-color: #409eff;
}
</style>
