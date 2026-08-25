/**
 * Mermaid 代码预处理工具
 *
 * 在将 LLM 生成的 mermaid 代码交给 mermaid.render 之前做语法清洗，
 * 修复常见导致 parse error 的写法（中文标点、节点标签特殊字符、
 * 误用的 classDiagram 箭头语法等）。纯函数，无 DOM 依赖，便于单测。
 *
 * 与 MarkdownRenderer.vue 的全量块渲染配合使用。
 */

// 检测 Mermaid 图表类型
const detectChartType = (code) => {
  const firstLine = code.trim().split('\n')[0].trim().toLowerCase()
  const chartTypes = [
    'quadrantChart', 'flowchart', 'graph', 'sequenceDiagram', 'classDiagram',
    'stateDiagram', 'erDiagram', 'gantt', 'pie', 'gitGraph', 'journey',
    'mindmap', 'timeline', 'requirementDiagram', 'C4Context', 'sankey',
    'xychart', 'treemap', 'block-beta', 'packet-beta', 'architecture-beta'
  ]

  for (const type of chartTypes) {
    const typeLower = type.toLowerCase()
    if (firstLine === typeLower || firstLine.startsWith(typeLower + ' ')) {
      return typeLower
    }
  }
  return 'unknown'
}

// 检查文本是否包含中文字符
const containsChinese = (text) => {
  return /[一-龥]/.test(text)
}

// 检查文本是否已被引号包裹
const isQuoted = (text) => {
  const trimmed = text.trim()
  return (trimmed.startsWith('"') && trimmed.endsWith('"')) ||
         (trimmed.startsWith("'") && trimmed.endsWith("'"))
}

// 为需要引号的文本添加引号
const quoteText = (text) => {
  const trimmed = text.trim()
  if (isQuoted(trimmed)) {
    return text // 已经有引号，不处理
  }
  // 使用英文双引号包裹
  return `"${trimmed}"`
}

// 根据图表类型为中文文本添加引号
const addQuotesForChineseText = (code, chartType) => {
  let processed = code
  const lines = processed.split('\n')
  const processedLines = lines.map((line, index) => {
    let processedLine = line

    // 通用处理：title 后的中文文本
    if (/^\s*title\s+/i.test(processedLine)) {
      processedLine = processedLine.replace(/^(\s*title\s+)(.+)$/i, (match, prefix, text) => {
        // 如果文本已引号包裹，不处理
        if (isQuoted(text)) return match
        // 如果包含中文或空格，添加引号
        if (containsChinese(text) || text.includes(' ')) {
          return prefix + quoteText(text)
        }
        return match
      })
    }

    // quadrantChart 特有处理
    if (chartType === 'quadrantchart') {
      // x-axis 和 y-axis 需要处理 --> 分隔符两侧的文本
      // 格式: x-axis left --> right 或 y-axis bottom --> top
      const processAxisLine = (line, axisPrefix) => {
        return line.replace(new RegExp(`^(\\s*${axisPrefix}\\s+)(.+)$`, 'i'), (match, prefix, text) => {
          if (text.includes('-->')) {
            // 处理 left --> right 格式，分别对两侧文本添加引号
            const parts = text.split(/\s*-->\s*/)
            const quotedParts = parts.map(part => {
              const trimmed = part.trim()
              if (isQuoted(trimmed)) return trimmed
              if (containsChinese(trimmed) || trimmed.includes(' ')) {
                return `"${trimmed}"`
              }
              return trimmed
            })
            return prefix + quotedParts.join(' --> ')
          }
          // 没有 --> 的情况，整体处理
          if (isQuoted(text)) return match
          if (containsChinese(text) || text.includes(' ')) {
            return prefix + quoteText(text)
          }
          return match
        })
      }

      if (/^\s*x-axis\s+/i.test(processedLine)) {
        processedLine = processAxisLine(processedLine, 'x-axis')
      }
      if (/^\s*y-axis\s+/i.test(processedLine)) {
        processedLine = processAxisLine(processedLine, 'y-axis')
      }
      // quadrant-1, quadrant-2 等
      if (/^\s*quadrant-\d+\s+/i.test(processedLine)) {
        processedLine = processedLine.replace(/^(\s*quadrant-\d+\s+)(.+)$/i, (match, prefix, text) => {
          if (isQuoted(text)) return match
          if (containsChinese(text) || text.includes(' ')) {
            return prefix + quoteText(text)
          }
          return match
        })
      }

      // 处理数据点格式：标签: [x, y]
      // 如果标签包含中文，需要引号包裹
      if (/: \[/.test(processedLine)) {
        processedLine = processedLine.replace(/^(\s*)([^:[\]]+)(:\s*\[[\d.,\s]+\])$/, (match, space, label, coords) => {
          const trimmedLabel = label.trim()
          if (isQuoted(trimmedLabel)) return match
          if (containsChinese(trimmedLabel)) {
            return `${space}"${trimmedLabel}"${coords}`
          }
          return match
        })
      }
    }

    // gantt 图表处理：任务名称
    if (chartType === 'gantt') {
      // 处理 section 名称
      if (/^\s*section\s+/i.test(processedLine)) {
        processedLine = processedLine.replace(/^(\s*section\s+)(.+)$/i, (match, prefix, text) => {
          if (isQuoted(text)) return match
          if (containsChinese(text) || text.includes(' ')) {
            return prefix + quoteText(text)
          }
          return match
        })
      }
    }

    // pie 图表处理
    if (chartType === 'pie') {
      // 处理扇区标签 "Key" : value 格式
      // 注意：pie 图表的标签通常在引号内，但如果是中文且未引号，需要处理
    }

    // mindmap 处理
    if (chartType === 'mindmap') {
      // mindmap 的中文节点通常用圆括号或方括号包裹
      // 如果节点内容包含中文且有空格，可能需要引号
    }

    // journey 处理
    if (chartType === 'journey') {
      // 处理 section 名称
      if (/^\s*section\s+/i.test(processedLine)) {
        processedLine = processedLine.replace(/^(\s*section\s+)(.+)$/i, (match, prefix, text) => {
          if (isQuoted(text)) return match
          if (containsChinese(text) || text.includes(' ')) {
            return prefix + quoteText(text)
          }
          return match
        })
      }
    }

    return processedLine
  })

  return processedLines.join('\n')
}

// Mermaid 代码预处理 - 修复常见语法问题
export const preprocessMermaidCode = (code) => {
  let processed = code

  // 1. 保留 <br/> 和 <br>（Mermaid 在双引号内支持换行）
  // 不再替换 <br> 标签

  // 2. 处理 HTML 实体 - 将常见实体转换为字符
  // 使用字符串拼接避免文件保存时 HTML 实体被自动转换
  processed = processed.replace(/&nbsp;/g, ' ')
  processed = processed.replace(new RegExp('&' + 'lt;', 'g'), '<')
  processed = processed.replace(new RegExp('&' + 'gt;', 'g'), '>')
  processed = processed.replace(new RegExp('&' + 'quot;', 'g'), "'")
  processed = processed.replace(new RegExp('&' + 'amp;', 'g'), '&')

  // 3. 处理可能导致解析问题的中文标点符号
  // 中文双引号：“” -> 英文单引号（避免与 Mermaid 语法冲突）
  processed = processed.replace(/[“”]/g, "'")
  // 中文单引号：‘’ -> 英文单引号
  processed = processed.replace(/[‘’]/g, "'")
  // 中文冒号：：-> 破折号（冒号在 Mermaid 中有特殊含义）
  processed = processed.replace(/：/g, ' - ')
  // 中文书名号：《》-> 移除
  processed = processed.replace(/《/g, '').replace(/》/g, '')
  // 中文全角分号 -> 换行（Mermaid 不识别全角分号，会触发 Lexical error；
  // 换行是所有图表类型通用的语句分隔符，安全）
  processed = processed.replace(/；/g, '\n')
  // 行尾半角分号 -> 移除（防御 LLM 偶发生成，避免词法错误）
  processed = processed.replace(/;\s*$/gm, '')

  // 4. 移除可能导致问题的不可见字符（零宽空格、BOM等）
  processed = processed.replace(/[​-‍﻿ ]/g, '')

  // 5. 处理节点标签中的特殊字符（方括号内的内容）
  // 对每个节点标签进行处理，确保内容安全
  // 注意：保留双引号！Mermaid 需要双引号来正确包裹包含中文和特殊字符的节点标签
  processed = processed.replace(/\[([^\]]*)\]/g, (match, content) => {
    let safe = content
    // 移除可能导致问题的 HTML 标签残留，但保留 <br> 标签
    safe = safe.replace(/<\/?(?!br\b)[a-zA-Z][^>]*>/gi, '')
    // 含 <br> 换行标签或圆括号 () 的节点必须用双引号包裹：
    // - '<' 否则会被词法分析器当作节点结束符，触发 Parse error（期望 TAGEND/STADIUMEND 等）
    // - '(' 否则会被当作圆角节点语法起始符，触发 Parse error（got 'PS'）
    if (/<br\s*\/?>/i.test(safe) || /[()]/.test(safe)) {
      // 内部双引号转义为单引号，避免与外层包裹引号冲突
      const escaped = safe.replace(/"/g, "'")
      return `["${escaped}"]`
    }
    return `[${safe}]`
  })

  // 6. 修复 flowchart/graph 中误用 classDiagram 箭头语法的问题
  //    classDiagram: <|-- (继承), ..|> (实现), --|> (继承), .. (依赖)
  //    flowchart:    --> (实线箭头), -.-> (虚线箭头), -- (实线), -.- (虚线)
  const chartType = detectChartType(processed)
  if (chartType === 'graph' || chartType === 'flowchart') {
    // <|-- 继承 → --> 实线箭头
    processed = processed.replace(/<\|--/g, '-->')
    // ..|> 实现 → -.-> 虚线箭头
    processed = processed.replace(/\.\.\|>/g, '-.->')
    // --|> 继承 → --> 实线箭头
    processed = processed.replace(/--\|>/g, '-->')
    // .. 依赖（独立行，非节点内） → -.- 虚线
    // 仅匹配 行首空格 + 节点ID + .. + 节点ID 的模式
    processed = processed.replace(/^(\s*\S+)\s+\.\.\s+(\S+)$/gm, '$1 -.- $2')
  }

  // 7. 为中文文本自动添加引号（根据图表类型）
  processed = addQuotesForChineseText(processed, chartType)

  return processed.trim()
}
