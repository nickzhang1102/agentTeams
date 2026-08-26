<template>
  <div class="markdown-renderer" :class="$attrs.class" ref="containerRef" v-html="sanitizedContent"></div>
  
  <!-- Mermaid 全屏查看 Modal -->
  <Teleport to="body">
    <Transition name="modal-fade">
      <div v-if="fullscreenMermaid.show" class="mermaid-fullscreen-modal" @click.self="closeFullscreen">
        <div class="mermaid-fullscreen-content">
          <div class="mermaid-fullscreen-header">
            <div class="mermaid-fullscreen-title">Mermaid 图表</div>
            <div class="mermaid-fullscreen-toolbar">
              <button class="mermaid-toolbar-btn" @click="zoomInFullscreen" title="放大">
                <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="11" cy="11" r="8"/>
                  <path d="M21 21l-4.35-4.35M11 8v6M8 11h6"/>
                </svg>
              </button>
              <button class="mermaid-toolbar-btn" @click="zoomOutFullscreen" title="缩小">
                <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="11" cy="11" r="8"/>
                  <path d="M21 21l-4.35-4.35M8 11h6"/>
                </svg>
              </button>
              <button class="mermaid-toolbar-btn" @click="resetFullscreenZoom" title="重置">
                <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
                  <path d="M3 3v5h5"/>
                </svg>
              </button>
              <span class="mermaid-zoom-level">{{ Math.round(fullscreenMermaid.zoom * 100) }}%</span>
              <button class="mermaid-toolbar-btn close-btn" @click="closeFullscreen" title="关闭">
                <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M18 6L6 18M6 6l12 12"/>
                </svg>
              </button>
            </div>
          </div>
          <div class="mermaid-fullscreen-body" ref="fullscreenBodyRef">
            <div
              class="mermaid-fullscreen-svg"
              v-html="sanitizedFullscreenSvg"
              :style="{ transform: `scale(${fullscreenMermaid.zoom})` }"
            ></div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { computed, ref, onMounted, onUnmounted, watch, nextTick, reactive } from 'vue'

// 禁用自动属性继承，因为组件有多个根节点
defineOptions({
  inheritAttrs: false
})
import { marked } from 'marked'
import hljs from 'highlight.js/lib/core'
import bash from 'highlight.js/lib/languages/bash'
import css from 'highlight.js/lib/languages/css'
import diff from 'highlight.js/lib/languages/diff'
import javascript from 'highlight.js/lib/languages/javascript'
import json from 'highlight.js/lib/languages/json'
import markdown from 'highlight.js/lib/languages/markdown'
import python from 'highlight.js/lib/languages/python'
import scss from 'highlight.js/lib/languages/scss'
import sql from 'highlight.js/lib/languages/sql'
import typescript from 'highlight.js/lib/languages/typescript'
import xml from 'highlight.js/lib/languages/xml'
import yaml from 'highlight.js/lib/languages/yaml'
import mermaid from 'mermaid'
import { preprocessMermaidCode } from '../utils/mermaidPreprocess'
import DOMPurify from 'dompurify'
import 'highlight.js/styles/github.css'

hljs.registerLanguage('bash', bash)
hljs.registerLanguage('sh', bash)
hljs.registerLanguage('shell', bash)
hljs.registerLanguage('css', css)
hljs.registerLanguage('diff', diff)
hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('js', javascript)
hljs.registerLanguage('json', json)
hljs.registerLanguage('markdown', markdown)
hljs.registerLanguage('md', markdown)
hljs.registerLanguage('python', python)
hljs.registerLanguage('py', python)
hljs.registerLanguage('scss', scss)
hljs.registerLanguage('sql', sql)
hljs.registerLanguage('typescript', typescript)
hljs.registerLanguage('ts', typescript)
hljs.registerLanguage('html', xml)
hljs.registerLanguage('vue', xml)
hljs.registerLanguage('xml', xml)
hljs.registerLanguage('yaml', yaml)
hljs.registerLanguage('yml', yaml)

// DOMPurify 配置：允许 Mermaid 图表所需的标签和属性
DOMPurify.addHook('uponSanitizeAttribute', (node, data) => {
  // 允许 data-* 属性（Mermaid 工具栏需要）
  if (data.attrName && data.attrName.startsWith('data-')) {
    data.forceKeepAttr = true
  }
})

const props = defineProps({
  content: {
    type: String,
    default: ''
  },
  streaming: {
    type: Boolean,
    default: false
  },
  evidenceMap: {
    type: [Array, Object],
    default: () => []
  },
  evidenceLabel: {
    type: String,
    default: 'evidence'
  }
})

const emit = defineEmits(['evidence-click'])

const containerRef = ref(null)
const fullscreenBodyRef = ref(null)
const mermaidIdCounter = ref(0)

// 全屏查看状态
const fullscreenMermaid = reactive({
  show: false,
  svg: '',
  zoom: 1
})

// XSS 安全过滤：全屏 SVG 内容净化
const sanitizedFullscreenSvg = computed(() => {
  const svg = fullscreenMermaid.svg
  if (!svg) return ''

  // 对 SVG 内容进行净化，过滤危险元素
  return DOMPurify.sanitize(svg, {
    ADD_TAGS: ['svg', 'g', 'path', 'rect', 'circle', 'ellipse', 'line', 'polygon', 'polyline', 'text', 'tspan', 'foreignObject', 'desc', 'title'],
    ADD_ATTR: ['viewBox', 'preserveAspectRatio', 'xmlns', 'xmlns:xlink', 'xlink:href', 'transform', 'transform-origin', 'fill', 'stroke', 'stroke-width', 'stroke-dasharray', 'd', 'x', 'y', 'width', 'height', 'rx', 'ry', 'cx', 'cy', 'r', 'x1', 'y1', 'x2', 'y2', 'points', 'text-anchor', 'font-size', 'font-family', 'font-weight', 'opacity', 'class', 'id', 'style'],
    FORBID_TAGS: ['script', 'iframe', 'object', 'embed', 'form', 'input', 'button'],
    FORBID_ATTR: ['onload', 'onerror', 'onclick', 'onmouseover', 'onmouseout', 'onkeydown', 'onkeyup', 'onfocus', 'onblur', 'srcdoc', 'formaction']
  })
})

// 初始化 mermaid
mermaid.initialize({
  startOnLoad: false,
  theme: 'default',
  securityLevel: 'loose',
  fontFamily: 'inherit',
  suppressErrorRendering: true,  // 抑制自动生成错误提示元素
  themeVariables: {
    fontSize: '15px'
  }
})

// 生成唯一 ID
const generateMermaidId = () => {
  return `mermaid-${Date.now()}-${mermaidIdCounter.value++}`
}

// HTML 转义函数
const escapeHtml = (text) => {
  const div = document.createElement('div')
  div.textContent = text
  return div.innerHTML
}


// 清理 Mermaid 自动生成的错误元素
const cleanupMermaidErrors = () => {
  // 清理页面底部和 body 下所有包含 Mermaid 错误信息的元素
  // Mermaid 11.x 版本会在 body 末尾生成错误提示 div
  
  // 方法1: 通过文本内容匹配清理
  const allElements = document.querySelectorAll('div, pre, span')
  allElements.forEach(el => {
    const text = el.textContent || ''
    // 匹配 Mermaid 错误特征文本
    if (text.includes('Syntax error in text') && text.includes('mermaid version')) {
      // 确保不是我们自己的错误提示容器
      if (!el.closest('.mermaid-container') && !el.closest('.mermaid-wrapper')) {
        el.remove()
      }
    }
  })
  
  // 方法2: 清理特定选择器的错误元素
  const errorSelectors = [
    '.mermaid-error:not(.mermaid-container .mermaid-error)',  // 非容器内的错误
    '[class*="mermaid"] > .error:not(.mermaid-container *)',
    '.d2h-wrapper',
    'pre[id^="d2h-"]',
    'div[class*="error"]:not(.mermaid-container *)'
  ]
  
  errorSelectors.forEach(selector => {
    try {
      document.querySelectorAll(selector).forEach(el => {
        if (el.textContent?.includes('Syntax error')) {
          el.remove()
        }
      })
    } catch (e) {
      // 忽略选择器错误
    }
  })
  
  // 方法3: 清理 body 直接子元素中的错误提示
  document.body.querySelectorAll(':scope > div').forEach(el => {
    const text = el.textContent || ''
    if (text.includes('Syntax error in text') && text.includes('mermaid version')) {
      el.remove()
    }
  })
  
  // 方法4: 清理容器内的残留错误（保留我们自定义的错误提示）
  if (containerRef.value) {
    containerRef.value.querySelectorAll('.mermaid-container').forEach(container => {
      // 只移除 Mermaid 自动生成的错误元素，保留我们的 .mermaid-error
      container.querySelectorAll(':scope > pre.error, :scope > div.error:not(.mermaid-error)').forEach(el => {
        if (el.textContent?.includes('Syntax error')) {
          el.remove()
        }
      })
    })
  }
}

// 存储当前渲染周期的 mermaid 代码
let currentRenderMermaidCodes = []

// 自定义渲染器
const renderer = new marked.Renderer()

// 存储待渲染的 mermaid 代码（流式输出期间）
const pendingMermaidCodes = ref([])

// 重写 codeBlock 渲染方法
renderer.code = function(code, language) {
  // 检测 mermaid 图表 - 支持所有 mermaid 图表类型
  // 语言标识可能是: mermaid, graph, graph TD, graph LR, flowchart, quadrantChart 等
  const mermaidLanguagePrefixes = [
    'mermaid', 'graph', 'flowchart', 'sequenceDiagram', 'classDiagram', 
    'stateDiagram', 'erDiagram', 'gantt', 'pie', 'gitGraph',
    'journey', 'mindmap', 'timeline', 'quadrantChart', 'requirementDiagram',
    'C4Context', 'block-beta', 'packet-beta', 'architecture-beta',
    'sankey', 'xychart', 'treemap'
  ]
  
  // 检查 language 是否匹配 mermaid 类型（精确匹配或前缀匹配，忽略大小写）
  const languageLower = language ? language.toLowerCase() : ''
  const isMermaidByLanguage = language && (
    languageLower === 'mermaid' ||
    mermaidLanguagePrefixes.some(prefix => 
      languageLower === prefix.toLowerCase() || languageLower.startsWith(prefix.toLowerCase() + ' ')
    )
  )
  
  // 额外检查：如果语言是 mermaid 但代码内容以图表类型关键字开头，也识别为 mermaid
  // 这可以处理某些解析器可能将第一行作为语言标识的情况
  const codeFirstLine = code.trim().split('\n')[0].trim().toLowerCase()
  const isMermaidByContent = codeFirstLine && mermaidLanguagePrefixes.some(prefix => 
    codeFirstLine === prefix.toLowerCase() || codeFirstLine.startsWith(prefix.toLowerCase())
  )
  
  const isMermaid = isMermaidByLanguage || isMermaidByContent
  
  // 如果语言标识是 mermaid 或匹配 mermaid 图表类型
  if (isMermaid) {
    const trimmedCode = code.trim()
    const id = generateMermaidId()
    
    // 流式输出时，显示占位符，但保存代码等待渲染
    if (props.streaming) {
      // 保存代码到待渲染列表
      pendingMermaidCodes.value.push({ id, code: trimmedCode })
      
      return `
        <div class="mermaid-wrapper">
          <div class="mermaid-container mermaid-pending" data-mermaid-id="${id}" data-zoom="1">
            <div class="mermaid-loading">正在渲染图表...</div>
          </div>
        </div>
      `
    }
    
    // 非流式输出时，渲染 mermaid 图表
    currentRenderMermaidCodes.push({ id, code: trimmedCode })
    return `
      <div class="mermaid-wrapper">
        <div class="mermaid-toolbar">
          <button class="mermaid-toolbar-btn" data-action="zoom-in" data-mermaid-id="${id}" title="放大">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="11" cy="11" r="8"/>
              <path d="M21 21l-4.35-4.35M11 8v6M8 11h6"/>
            </svg>
          </button>
          <button class="mermaid-toolbar-btn" data-action="zoom-out" data-mermaid-id="${id}" title="缩小">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="11" cy="11" r="8"/>
              <path d="M21 21l-4.35-4.35M8 11h6"/>
            </svg>
          </button>
          <button class="mermaid-toolbar-btn" data-action="reset" data-mermaid-id="${id}" title="重置">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
              <path d="M3 3v5h5"/>
            </svg>
          </button>
          <button class="mermaid-toolbar-btn" data-action="fullscreen" data-mermaid-id="${id}" title="全屏查看">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M8 3H5a2 2 0 0 0-2 2v3M21 8V5a2 2 0 0 0-2-2h-3M3 16v3a2 2 0 0 0 2 2h3M16 21h3a2 2 0 0 0 2-2v-3"/>
            </svg>
          </button>
        </div>
        <div class="mermaid-container" data-mermaid-id="${id}" data-zoom="1">
          <div class="mermaid-loading">正在渲染图表...</div>
        </div>
      </div>
    `
  }
  
  // 普通代码块高亮
  let highlighted
  if (language && hljs.getLanguage(language)) {
    try {
      highlighted = hljs.highlight(code, { language }).value
    } catch (err) {
      highlighted = hljs.highlightAuto(code).value
    }
  } else {
    highlighted = hljs.highlightAuto(code).value
  }
  
  // 添加内联样式确保换行
  return `<pre style="white-space: pre-wrap; word-wrap: break-word; overflow-wrap: break-word; word-break: break-word; overflow-x: hidden;"><code class="hljs language-${language || ''}" style="white-space: pre-wrap; word-wrap: break-word; overflow-wrap: break-word; word-break: break-word;">${highlighted}</code></pre>`
}

// 显式引用是当前协议；裸 ID 仅用于兼容历史报告。两者都必须存在于
// 当前报告的 evidence_map 中才会转成可点击引用，避免误伤正文变量名。
const _EV_REF_RE = /\[evidence_id:([^\]\s]+)\]|\b((?:[a-z0-9_-]+_)?ev_[a-z0-9_]+_\d+)\b/gi

const normalizedEvidence = computed(() => {
  const evidence = Array.isArray(props.evidenceMap)
    ? props.evidenceMap
    : Object.values(props.evidenceMap || {})

  return evidence.filter(item => item && typeof item === 'object' && item.evidence_id)
})

const evidenceLookup = computed(() => {
  const lookup = new Map()
  normalizedEvidence.value.forEach((item, index) => {
    const evidenceId = String(item.evidence_id).trim()
    if (evidenceId && !lookup.has(evidenceId)) {
      lookup.set(evidenceId, { item, number: index + 1 })
    }
  })
  return lookup
})

const escapeAttribute = (value) => String(value ?? '')
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;')

const decodeTextEntities = (text) => text
  .replace(/&lt;/g, '<')
  .replace(/&gt;/g, '>')
  .replace(/&quot;/g, '"')
  .replace(/&#39;/g, "'")
  .replace(/&amp;/g, '&')

// 重写 text 渲染方法：识别 evidence ID 并标记为可点击元素
renderer.text = function (text) {
  // Decode already-escaped text entities first, then escape all raw text for XSS safety.
  const safe = decodeTextEntities(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
  return safe.replace(_EV_REF_RE, (match, explicitId, legacyId) => {
    const evidenceId = explicitId || legacyId
    const evidence = evidenceLookup.value.get(evidenceId)
    if (!evidence) return match

    const label = `${props.evidenceLabel}${evidence.number}`
    const title = evidence.item.title || label
    return `<button type="button" class="evidence-ref" data-evidence-id="${escapeAttribute(evidenceId)}" title="${escapeAttribute(title)}" aria-label="${escapeAttribute(label)}">${escapeAttribute(label)}</button>`
  })
}

// 修复中文场景下 **bold** / *em* 紧贴标点导致闭合定界符不被识别的问题
//
// 根因：marked v11 严格遵循 CommonMark 强调定界符规则。`）**是` 这类
// `[Unicode 标点]**[非标点非空白]` 模式，被 emStrongRDelimAst 规则 (3) 判定为
// "仅左定界符"（#***a 型），导致 `**加粗内容）**后续中文` 中的闭合 `**` 永远
// 找不到匹配的右定界符，`**` 原样输出为字面量。
//
// 解法：在符合该模式的 `*` 串前插入零宽空格 U+200B，把"前导 Unicode 标点"
// 破坏为"非标点字符"，使该 `*` 串落入规则 (6) "可左可右"分支，从而正确闭合。
// 零宽空格不可见，渲染无视觉影响。代码块/行内代码内的 `*` 不做处理。
// 注意：前导字符排除 `*` 自身，否则会把 `**` 的首个 `*` 当成前导标点。
const fixCjkEmphasisDelimiters = (content) => {
  if (!content || typeof content !== 'string') return content

  // 按代码块/行内代码切分，仅对非代码段做处理，避免误伤代码中的 `*`
  const codeRegex = /```[\s\S]*?```|`[^`\n]*`/g
  const segments = []
  let last = 0
  let m
  while ((m = codeRegex.exec(content)) !== null) {
    if (m.index > last) segments.push(content.slice(last, m.index))
    segments.push(m[0])
    last = m.index + m[0].length
  }
  if (last < content.length) segments.push(content.slice(last))

  return segments.map((seg, i) => {
    // 偶数下标为非代码段（首段必为文本），奇数下标为代码段原样保留
    return i % 2 === 1
      ? seg
      : seg.replace(/(?!\*)(\p{P})(\*+)(?=[^\p{P}\s])/gu, '$1\u200B$2')
  }).join('')
}

// 重写 link 渲染方法：自动补全协议前缀，外部链接新窗口打开
renderer.link = function(href, title, text) {
  let url = href || ''

  // 自动补全 https:// 协议前缀（LLM 可能生成无协议的裸域名）
  if (url && !/^(https?|mailto|tel):/i.test(url) && !url.startsWith('#') && !url.startsWith('/')) {
    url = 'https://' + url
  }

  const titleAttr = title ? ` title="${title}"` : ''
  // 外部链接新窗口打开
  if (/^https?:\/\//i.test(url)) {
    return `<a href="${url}"${titleAttr} target="_blank" rel="noopener noreferrer">${text}</a>`
  }
  return `<a href="${url}"${titleAttr}>${text}</a>`
}

// 配置 marked
marked.setOptions({
  renderer: renderer,
  breaks: true,
  gfm: true
})

// 用于渲染的 mermaid 代码存储
const mermaidCodesForRender = ref([])

// 存储 SVG 内容（用于全屏查看）
const mermaidSvgs = ref({})

const renderedContent = computed(() => {
  if (!props.content) return ''
  // 防御：确保 content 为字符串，避免 JSONB 对象传入 marked 导致报错
  const contentStr = typeof props.content === 'string'
    ? props.content
    : JSON.stringify(props.content, null, 2)
  // 清空当前渲染周期的 mermaid 代码
  currentRenderMermaidCodes = []
  const result = marked(fixCjkEmphasisDelimiters(contentStr))
  // 将当前渲染周期的数据保存到响应式变量
  mermaidCodesForRender.value = [...currentRenderMermaidCodes]
  return result
})

const promoteSingleEvidenceBlocks = (html) => {
  const wrapper = document.createElement('div')
  wrapper.innerHTML = html

  const decorateLinkedContent = (element, evidenceId, title) => {
    element.classList.add('evidence-linked-content')
    element.dataset.evidenceId = evidenceId
    element.setAttribute('role', 'link')
    element.setAttribute('tabindex', '0')
    element.setAttribute('title', title)
    element.setAttribute('aria-label', `${element.textContent.trim()} — ${title}`)
  }

  wrapper.querySelectorAll('p, li, td, th').forEach(block => {
    const refs = Array.from(block.querySelectorAll('.evidence-ref'))
      .filter(ref => ref.closest('p, li, td, th') === block)
    const evidenceIds = [...new Set(refs.map(ref => ref.dataset.evidenceId).filter(Boolean))]

    if (evidenceIds.length !== 1 || block.textContent.includes('[evidence_id:')) return

    const title = refs.find(ref => ref.title)?.title || props.evidenceLabel
    refs.forEach(ref => ref.remove())
    decorateLinkedContent(block, evidenceIds[0], title)
  })

  const promoteLooseSegment = (nodes) => {
    const refs = nodes.flatMap(node => {
      if (node.nodeType !== Node.ELEMENT_NODE) return []
      return [
        ...(node.matches('.evidence-ref') ? [node] : []),
        ...node.querySelectorAll('.evidence-ref')
      ]
    })
    const evidenceIds = [...new Set(refs.map(ref => ref.dataset.evidenceId).filter(Boolean))]
    const segmentText = nodes.map(node => node.textContent || '').join('')

    if (!refs.length || evidenceIds.length !== 1 || segmentText.includes('[evidence_id:')) return

    const linkedContent = document.createElement('span')
    const title = refs.find(ref => ref.title)?.title || props.evidenceLabel
    const contentNodes = nodes.filter(node => !refs.includes(node))
    refs.forEach(ref => ref.remove())
    if (!contentNodes.some(node => node.textContent.trim())) return

    contentNodes[0].before(linkedContent)
    contentNodes.forEach(node => linkedContent.append(node))
    decorateLinkedContent(linkedContent, evidenceIds[0], title)
  }

  const looseBoundarySelector = 'br, div, section, article, h1, h2, h3, h4, h5, h6, p, ul, ol, pre, table, blockquote, hr'
  let looseSegment = []
  Array.from(wrapper.childNodes).forEach(node => {
    if (node.nodeType === Node.ELEMENT_NODE && node.matches(looseBoundarySelector)) {
      promoteLooseSegment(looseSegment)
      looseSegment = []
      return
    }
    looseSegment.push(node)
  })
  promoteLooseSegment(looseSegment)

  return wrapper.innerHTML
}

// XSS 安全过滤：使用 DOMPurify 清理 HTML 内容
const sanitizedContent = computed(() => {
  const rawContent = renderedContent.value
  if (!rawContent) return ''

  // DOMPurify 配置：保留 Mermaid 图表所需的标签和属性
  const sanitized = DOMPurify.sanitize(rawContent, {
    // 允许的标签（在默认白名单基础上添加）
    ADD_TAGS: [
      'mermaid',           // Mermaid 自定义标签（如有）
      'foreignObject',     // SVG 内嵌外部对象
      'desc',              // SVG 描述
      'title'              // SVG 标题
    ],
    // 允许的属性（在默认白名单基础上添加）
    ADD_ATTR: [
      'data-mermaid-id',   // Mermaid 容器 ID
      'data-action',       // 工具栏按钮动作
      'data-zoom',         // 缩放级别
      'target',            // 链接 target 属性
      'viewBox',           // SVG viewBox
      'preserveAspectRatio', // SVG preserveAspectRatio
      'xmlns',             // SVG xmlns
      'xmlns:xlink',       // SVG xlink
      'xlink:href',        // SVG xlink:href
      'transform',         // SVG transform
      'transform-origin',  // CSS transform-origin
      'class'              // class 属性（DOMPurify 默认允许）
    ],
    // 允许 data-* 通配符属性
    FORBID_ATTR: [],       // 不禁止任何属性
    // 允许 SVG 内的 foreignObject（Mermaid 可能用到）
    FORCE_BODY: false,     // 允许在 svg 内使用 foreignObject
    // 返回完整文档而非 body 内容（保留 SVG 结构）
    WHOLE_DOCUMENT: false,
    // 允许 SVG 命名空间
    // 注：不再将 xlink:href 加入 ADD_URI_SAFE_ATTR——保留 DOMPurify 的
    // URI 协议校验（javascript: 等危险协议仍被拦截），正常 http(s) 链接受影响
  })

  return promoteSingleEvidenceBlocks(sanitized)
})

// 渲染 mermaid 图表
const renderMermaidCharts = async () => {
  await nextTick()
  
  if (!containerRef.value) {
    return
  }
  
  // 先清理可能残留的错误元素
  cleanupMermaidErrors()
  
  const containers = containerRef.value.querySelectorAll('.mermaid-container')
  
  for (const container of containers) {
    const id = container.dataset.mermaidId
    const mermaidData = mermaidCodesForRender.value.find(m => m.id === id)
    
    if (!mermaidData) {
      continue
    }
    
    // 预处理 Mermaid 代码
    const processedCode = preprocessMermaidCode(mermaidData.code)
    
    try {
      const { svg } = await mermaid.render(id, processedCode)
      container.innerHTML = svg
      // 保存 SVG 用于全屏查看
      mermaidSvgs.value[id] = svg
      // 清理可能产生的错误元素
      cleanupMermaidErrors()
    } catch (error) {
      // 渲染失败时，显示友好的错误提示
      const errorMsg = error?.message || '未知错误'
      container.innerHTML = `
        <div class="mermaid-error">
          <div class="mermaid-error-title">⚠️ 图表渲染失败</div>
          <div class="mermaid-error-message">图表语法可能包含不支持的格式，请检查以下代码：</div>
          <pre class="mermaid-error-code"><code>${escapeHtml(mermaidData.code)}</code></pre>
          <div class="mermaid-error-detail" style="font-size: 12px; color: #909399; margin-top: 8px;">错误详情：${escapeHtml(errorMsg)}</div>
        </div>
      `
      // 清理 Mermaid 自动生成的错误元素
      cleanupMermaidErrors()
    }
  }
  
  // 最终清理一次
  cleanupMermaidErrors()
}

// 处理工具栏按钮点击（复用同一容器 click 监听，兼处理证据引用）
const handleToolbarClick = (event) => {
  // 证据引用点击
  const evRef = event.target.closest('.evidence-ref')
  if (evRef) {
    const evidenceId = evRef.dataset.evidenceId
    if (evidenceId) {
      emit('evidence-click', evidenceId)
    }
    return
  }

  const linkedContent = event.target.closest('.evidence-linked-content')
  const nestedControl = event.target.closest('a, button, input, select, textarea')
  if (linkedContent && !nestedControl) {
    const evidenceId = linkedContent.dataset.evidenceId
    if (evidenceId) {
      emit('evidence-click', evidenceId)
    }
    return
  }

  const btn = event.target.closest('.mermaid-toolbar-btn')
  if (!btn) return
  
  const action = btn.dataset.action
  const mermaidId = btn.dataset.mermaidId
  const container = containerRef.value?.querySelector(`.mermaid-container[data-mermaid-id="${mermaidId}"]`)
  
  if (!container) return
  
  let zoom = parseFloat(container.dataset.zoom) || 1
  
  switch (action) {
    case 'zoom-in':
      zoom = Math.min(zoom + 0.25, 10)
      break
    case 'zoom-out':
      zoom = Math.max(zoom - 0.25, 0.5)
      break
    case 'reset':
      zoom = 1
      break
    case 'fullscreen':
      openFullscreen(mermaidId)
      return
  }
  
  container.dataset.zoom = zoom
  const svgElement = container.querySelector('svg')
  if (svgElement) {
    svgElement.style.transform = `scale(${zoom})`
    svgElement.style.transformOrigin = 'center center'
  }
}

const handleEvidenceKeydown = (event) => {
  if (event.key !== 'Enter' && event.key !== ' ') return
  const linkedContent = event.target.closest('.evidence-linked-content')
  if (!linkedContent || event.target !== linkedContent) return

  const evidenceId = linkedContent.dataset.evidenceId
  if (!evidenceId) return
  event.preventDefault()
  emit('evidence-click', evidenceId)
}

// 打开全屏查看
const openFullscreen = (mermaidId) => {
  const svg = mermaidSvgs.value[mermaidId]
  if (!svg) return
  
  fullscreenMermaid.svg = svg
  fullscreenMermaid.zoom = 3  // 默认放大到 300%
  fullscreenMermaid.show = true
  document.body.style.overflow = 'hidden'
}

// 关闭全屏查看
const closeFullscreen = () => {
  fullscreenMermaid.show = false
  fullscreenMermaid.svg = ''
  document.body.style.overflow = ''
}

// 全屏模式缩放
const zoomInFullscreen = () => {
  fullscreenMermaid.zoom = Math.min(fullscreenMermaid.zoom + 0.25, 10)
}

const zoomOutFullscreen = () => {
  fullscreenMermaid.zoom = Math.max(fullscreenMermaid.zoom - 0.25, 0.25)
}

const resetFullscreenZoom = () => {
  fullscreenMermaid.zoom = 1
}

// ESC 键关闭全屏
const handleKeydown = (event) => {
  if (event.key === 'Escape' && fullscreenMermaid.show) {
    closeFullscreen()
  }
}

// 渲染待渲染的 mermaid 图表（流式输出完成后）
const renderPendingMermaidCharts = async () => {
  await nextTick()
  
  if (!containerRef.value || pendingMermaidCodes.value.length === 0) {
    return
  }
  
  // 先清理可能残留的错误元素
  cleanupMermaidErrors()
  
  // 获取所有待渲染的容器
  const containers = containerRef.value.querySelectorAll('.mermaid-container.mermaid-pending')
  
  for (const container of containers) {
    const id = container.dataset.mermaidId
    const mermaidData = pendingMermaidCodes.value.find(m => m.id === id)
    
    if (!mermaidData) {
      continue
    }
    
    // 预处理 Mermaid 代码
    const processedCode = preprocessMermaidCode(mermaidData.code)
    
    try {
      const { svg } = await mermaid.render(id, processedCode)
      container.innerHTML = svg
      container.classList.remove('mermaid-pending')
      // 保存 SVG 用于全屏查看
      mermaidSvgs.value[id] = svg
      // 清理可能产生的错误元素
      cleanupMermaidErrors()
    } catch (error) {
      // 渲染失败时，显示友好的错误提示
      const errorMsg = error?.message || '未知错误'
      container.innerHTML = `
        <div class="mermaid-error">
          <div class="mermaid-error-title">⚠️ 图表渲染失败</div>
          <div class="mermaid-error-message">图表语法可能包含不支持的格式，请检查以下代码：</div>
          <pre class="mermaid-error-code"><code>${escapeHtml(mermaidData.code)}</code></pre>
          <div class="mermaid-error-detail" style="font-size: 12px; color: #909399; margin-top: 8px;">错误详情：${escapeHtml(errorMsg)}</div>
        </div>
      `
      container.classList.remove('mermaid-pending')
      // 清理 Mermaid 自动生成的错误元素
      cleanupMermaidErrors()
    }
  }
  
  // 清空待渲染列表
  pendingMermaidCodes.value = []
  
  // 最终清理一次
  cleanupMermaidErrors()
}

// 监听 streaming 状态变化
watch(() => props.streaming, (newVal, oldVal) => {
  // 当 streaming 从 true 变为 false 时，渲染待渲染的图表
  if (oldVal === true && newVal === false) {
    renderPendingMermaidCharts()
  }
})

// 监听内容变化 - 使用 flush: 'post' 确保在 DOM 更新后执行
watch(() => props.content, () => {
  // 非流式输出时才渲染
  if (!props.streaming) {
    renderMermaidCharts()
  }
}, { flush: 'post' })

// 组件挂载后渲染
onMounted(() => {
  renderMermaidCharts()
  containerRef.value?.addEventListener('click', handleToolbarClick)
  containerRef.value?.addEventListener('keydown', handleEvidenceKeydown)
  document.addEventListener('keydown', handleKeydown)
})

// 组件卸载时清理
onUnmounted(() => {
  containerRef.value?.removeEventListener('click', handleToolbarClick)
  containerRef.value?.removeEventListener('keydown', handleEvidenceKeydown)
  document.removeEventListener('keydown', handleKeydown)
  // 清理可能残留的错误元素
  cleanupMermaidErrors()
  // 关闭全屏模式（如果打开的话）
  if (fullscreenMermaid.show) {
    document.body.style.overflow = ''
  }
})
</script>

<style scoped>
.markdown-renderer {
  line-height: 1.6;
  word-wrap: break-word;
  overflow-wrap: break-word;
  word-break: break-word;
}

.markdown-renderer :deep(h1),
.markdown-renderer :deep(h2),
.markdown-renderer :deep(h3),
.markdown-renderer :deep(h4),
.markdown-renderer :deep(h5),
.markdown-renderer :deep(h6) {
  margin-top: 24px;
  margin-bottom: 16px;
  font-weight: 600;
  line-height: 1.25;
}

.markdown-renderer :deep(h1) {
  font-size: 2em;
  border-bottom: 1px solid #eaecef;
  padding-bottom: 0.3em;
}

.markdown-renderer :deep(h2) {
  font-size: 1.5em;
  border-bottom: 1px solid #eaecef;
  padding-bottom: 0.3em;
}

.markdown-renderer :deep(h3) {
  font-size: 1.25em;
}

.markdown-renderer :deep(p) {
  margin-bottom: 16px;
}

.markdown-renderer :deep(code) {
  padding: 0.2em 0.4em;
  margin: 0;
  font-size: 100%;
  background-color: rgba(27, 31, 35, 0.05);
  border-radius: 3px;
  word-wrap: break-word;
  overflow-wrap: break-word;
  word-break: break-word;
}

.markdown-renderer :deep(pre) {
  padding: 16px;
  overflow-x: hidden;
  font-size: 100%;
  line-height: 1.45;
  background-color: #f6f8fa;
  border-radius: 6px;
  margin-bottom: 16px;
  white-space: pre-wrap !important;
  word-wrap: break-word !important;
  overflow-wrap: break-word !important;
  word-break: break-word !important;
}

.markdown-renderer :deep(pre code) {
  background-color: transparent;
  padding: 0;
  white-space: pre-wrap !important;
  word-wrap: break-word !important;
  overflow-wrap: break-word !important;
  word-break: break-word !important;
}

.markdown-renderer :deep(ul),
.markdown-renderer :deep(ol) {
  padding-left: 2em;
  margin-bottom: 16px;
}

.markdown-renderer :deep(li) {
  margin-bottom: 0.25em;
}

.markdown-renderer :deep(blockquote) {
  padding: 0 1em;
  color: #6a737d;
  border-left: 0.25em solid #dfe2e5;
  margin-bottom: 16px;
}

.markdown-renderer :deep(a) {
  color: #0366d6;
  text-decoration: none;
  word-wrap: break-word;
  overflow-wrap: break-word;
  word-break: break-word;
}

.markdown-renderer :deep(a:hover) {
  text-decoration: underline;
}

.markdown-renderer :deep(table) {
  border-spacing: 0;
  border-collapse: collapse;
  margin-bottom: 16px;
}

.markdown-renderer :deep(table th),
.markdown-renderer :deep(table td) {
  padding: 6px 13px;
  border: 1px solid var(--el-border-color);
  word-wrap: break-word;
  overflow-wrap: break-word;
}

.markdown-renderer :deep(table th) {
  font-weight: 600;
  background-color: var(--el-fill-color-light);
  color: var(--el-text-color-primary);
}

.markdown-renderer :deep(table tr:nth-child(2n)) {
  background-color: var(--el-fill-color-lighter);
}

.markdown-renderer :deep(img) {
  max-width: 100%;
  box-sizing: content-box;
  background-color: var(--el-bg-color);
}

.markdown-renderer :deep(hr) {
  height: 0.25em;
  padding: 0;
  margin: 24px 0;
  background-color: var(--el-border-color);
  border: 0;
}

/* 证据引用可点击样式 */
.markdown-renderer :deep(.evidence-ref) {
  display: inline;
  padding: 0;
  border: 0;
  color: var(--el-color-primary);
  cursor: pointer;
  border-bottom: 1px dashed var(--el-color-primary-light-3);
  background: transparent;
  font-family: inherit;
  font-size: 0.9em;
  line-height: inherit;
  transition: border-color 0.2s;
}
.markdown-renderer :deep(.evidence-ref:hover) {
  border-bottom-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.markdown-renderer :deep(.evidence-ref:focus-visible) {
  outline: 2px solid var(--el-color-primary-light-3);
  outline-offset: 2px;
}

/* 单一证据归属明确时，正文自身就是证据入口，不再追加引用标签。 */
.markdown-renderer :deep(.evidence-linked-content) {
  cursor: pointer;
  text-decoration-line: underline;
  text-decoration-style: dotted;
  text-decoration-color: var(--el-color-primary-light-3);
  text-underline-offset: 3px;
  transition: background-color 0.2s, text-decoration-color 0.2s;
}
.markdown-renderer :deep(.evidence-linked-content:hover) {
  background-color: var(--el-color-primary-light-9);
  text-decoration-color: var(--el-color-primary);
}
.markdown-renderer :deep(.evidence-linked-content:focus-visible) {
  outline: 2px solid var(--el-color-primary-light-3);
  outline-offset: 2px;
}

/* Mermaid 图表包装器 */
.markdown-renderer :deep(.mermaid-wrapper) {
  position: relative;
  margin: 20px 0;
}

/* Mermaid 工具栏 */
.markdown-renderer :deep(.mermaid-toolbar) {
  position: absolute;
  top: 8px;
  right: 8px;
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.2s ease;
  z-index: 10;
  background: rgba(255, 255, 255, 0.95);
  border-radius: 6px;
  padding: 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.markdown-renderer :deep(.mermaid-wrapper:hover .mermaid-toolbar) {
  opacity: 1;
}

.markdown-renderer :deep(.mermaid-toolbar-btn) {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  border-radius: 4px;
  cursor: pointer;
  color: #606266;
  transition: all 0.2s ease;
}

.markdown-renderer :deep(.mermaid-toolbar-btn:hover) {
  background: #ecf5ff;
  color: #409eff;
}

/* Mermaid 图表容器 */
.markdown-renderer :deep(.mermaid-container) {
  padding: 20px;
  background-color: #fafafa;
  border-radius: 8px;
  border: 1px solid #eaecef;
  overflow-x: auto;
  text-align: center;
}

.markdown-renderer :deep(.mermaid-container svg) {
  max-width: 100%;
  height: auto;
  transition: transform 0.2s ease;
}

.markdown-renderer :deep(.mermaid-loading) {
  padding: 40px;
  color: #909399;
  font-size: 14px;
}

.markdown-renderer :deep(.mermaid-error) {
  padding: 16px;
  background-color: #fef0f0;
  border-radius: 4px;
  border: 1px solid #fbc4c4;
  text-align: left;
}

.markdown-renderer :deep(.mermaid-error-title) {
  color: #f56c6c;
  font-weight: 600;
  margin-bottom: 12px;
}

.markdown-renderer :deep(.mermaid-error-code) {
  padding: 12px;
  background-color: #fff;
  border-radius: 4px;
  font-size: 12px;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
  margin-bottom: 12px;
}

.markdown-renderer :deep(.mermaid-error-message) {
  color: #909399;
  font-size: 12px;
}

/* 全屏 Modal 样式 */
.mermaid-fullscreen-modal {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.85);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  padding: 0;
}

.mermaid-fullscreen-content {
  background: #fff;
  border-radius: 0;
  width: 100vw;
  height: 100vh;
  max-width: 100vw;
  max-height: 100vh;
  display: flex;
  flex-direction: column;
  box-shadow: none;
}

.mermaid-fullscreen-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid #eaecef;
  flex-shrink: 0;
}

.mermaid-fullscreen-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.mermaid-fullscreen-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
}

.mermaid-fullscreen-toolbar .mermaid-toolbar-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  border-radius: 6px;
  cursor: pointer;
  color: #606266;
  transition: all 0.2s ease;
}

.mermaid-fullscreen-toolbar .mermaid-toolbar-btn:hover {
  background: #ecf5ff;
  color: #409eff;
}

.mermaid-fullscreen-toolbar .close-btn:hover {
  background: #fef0f0;
  color: #f56c6c;
}

.mermaid-zoom-level {
  font-size: 13px;
  color: #909399;
  min-width: 50px;
  text-align: center;
}

.mermaid-fullscreen-body {
  padding: 20px;
  overflow: auto;
  flex: 1;
  min-height: 300px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.mermaid-fullscreen-svg {
  transition: transform 0.2s ease;
  transform-origin: center center;
}

.mermaid-fullscreen-svg :deep(svg) {
  max-width: none;
  height: auto;
}

/* Modal 动画 */
.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.3s ease;
}

.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}

.modal-fade-enter-active .mermaid-fullscreen-content,
.modal-fade-leave-active .mermaid-fullscreen-content {
  transition: transform 0.3s ease;
}

.modal-fade-enter-from .mermaid-fullscreen-content,
.modal-fade-leave-to .mermaid-fullscreen-content {
  transform: scale(0.9);
}
</style>
