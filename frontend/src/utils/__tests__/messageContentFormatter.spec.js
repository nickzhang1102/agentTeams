import { describe, expect, it } from 'vitest'

import { formatMessageContent } from '../messageContentFormatter'


describe('messageContentFormatter locale', () => {
  it('formats an English assessment without Chinese display labels', () => {
    const formatted = formatMessageContent({
      score: 72,
      details: {
        analysis: 'The request is sufficiently complete.',
        scores: { '目标明确性': 30 }
      },
      risk_level: 'medium',
      risk_reason: 'The impact is limited.',
      content_locale: 'en-US'
    }, 'assessment')

    expect(formatted).toContain('## Requirement Assessment')
    expect(formatted).toContain('Goal clarity: 30 points')
    expect(formatted).toContain('**Risk Level**: Medium risk')
    expect(formatted).not.toContain('需求评估')
    expect(formatted).not.toContain(' 分')
  })

  it('formats an English follow-up heading from the persisted locale', () => {
    const formatted = formatMessageContent({
      questions: [{ question: 'What outcome do you need?', options: ['A', 'B'] }]
    }, 'question', 'en-US')

    expect(formatted).toContain('## Follow-up Questions')
    expect(formatted).toContain('What outcome do you need?')
  })

  it('formats an English answer heading from the persisted locale', () => {
    const formatted = formatMessageContent({
      answers: [{ question: 'Which target?', answer: 'Existing cluster' }]
    }, 'answer', 'en-US')

    expect(formatted).toContain('## User Answers')
    expect(formatted).not.toContain('用户回答')
  })

  it('formats English team progress and team configuration labels', () => {
    const progress = formatMessageContent({
      phase: 'selection_complete',
      content: 'The selected experts will collaborate on the rollout plan.',
      content_locale: 'en-US'
    }, 'progress')
    const team = formatMessageContent({
      team: {
        name: 'Smart team - Compare rollout options',
        description: 'The selected experts will collaborate on the rollout plan.',
        agents: [{ agent_name: 'Research Analyst', reason: 'Covers market evidence.' }]
      },
      content_locale: 'en-US'
    }, 'team_config')

    expect(progress).toContain('## Selection complete')
    expect(progress).not.toContain('选择完成')
    expect(team).toContain('## Team configuration complete')
    expect(team).toContain('**Team strategy**')
    expect(team).toContain('**Team members**')
    expect(team).not.toContain('团队配置完成')
  })
})
