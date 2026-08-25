import { describe, it, expect } from 'vitest'
import { preprocessMermaidCode } from './mermaidPreprocess'

// 复现用户报告的 mermaid 渲染失败：
//   Parse error on line 3: ... B --> C[MAPK通路 (RAS-RAF-MEK-ERK)]
//   Expecting 'SQE', ..., got 'PS'   （PS = 左括号）
//
// 根因：mermaid 把 [] 节点标签内的裸 ( 误解析为圆角节点语法起始符。
// 修复：节点标签内含 () 时，用双引号包裹整个标签内容。
describe('preprocessMermaidCode - 节点标签含圆括号', () => {
  it('含 () 的中文节点标签应用双引号包裹', () => {
    const code = `graph TD
    B --> C[MAPK通路 (RAS-RAF-MEK-ERK)]`
    const result = preprocessMermaidCode(code)
    expect(result).toContain('C["MAPK通路 (RAS-RAF-MEK-ERK)"]')
  })

  it('含 () 的英文节点标签也应加双引号', () => {
    const code = `graph TD
    A --> B[foo (bar) baz]`
    const result = preprocessMermaidCode(code)
    expect(result).toContain('B["foo (bar) baz"]')
  })

  it('用户报告的 KRAS 图表：所有含括号节点应全部加引号包裹', () => {
    const code = `graph TD
    A[KRAS G12D突变] --> B{经典下游通路激活}；
    B --> C[MAPK通路 (RAS-RAF-MEK-ERK)];
    B --> D[PI3K-AKT-mTOR通路];
    F --> G[高增殖活性 (Ki-67可能很高)]；
    J --> K[同源重组修复缺陷 (HRD)];
    M --> N[核苷酸切除修复 (NER) 缺陷];`
    const result = preprocessMermaidCode(code)
    expect(result).toContain('C["MAPK通路 (RAS-RAF-MEK-ERK)"]')
    expect(result).toContain('G["高增殖活性 (Ki-67可能很高)"]')
    expect(result).toContain('K["同源重组修复缺陷 (HRD)"]')
    expect(result).toContain('N["核苷酸切除修复 (NER) 缺陷"]')
  })
})
