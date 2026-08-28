import { beforeEach, describe, expect, it } from 'vitest'
import { embedApiPrefix, resolveEmbedPrefix, resolveHistoryBase } from '@/utils/embedBase'

describe('embedBase', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/')
  })

  describe('resolveEmbedPrefix', () => {
    it('returns empty prefix for unprefixed embed paths', () => {
      expect(resolveEmbedPrefix('/embed/conversation/token')).toBe('')
    })

    it('derives the host mount prefix from the path structure', () => {
      expect(resolveEmbedPrefix('/agentteams/embed/conversation/token')).toBe('/agentteams')
    })

    it('supports multi-segment host prefixes', () => {
      expect(resolveEmbedPrefix('/apps/agentteams/embed/conversation/token')).toBe('/apps/agentteams')
    })

    it('returns null outside embed paths', () => {
      expect(resolveEmbedPrefix('/dashboard')).toBeNull()
      expect(resolveEmbedPrefix('/login')).toBeNull()
      expect(resolveEmbedPrefix('/embedx/conversation/token')).toBeNull()
      expect(resolveEmbedPrefix('')).toBeNull()
    })
  })

  describe('resolveHistoryBase', () => {
    it('uses the host prefix as history base when embedded', () => {
      window.history.replaceState({}, '', '/agentteams/embed/conversation/token')
      expect(resolveHistoryBase()).toBe('/agentteams/')
    })

    it('falls back to root base for standalone deployment', () => {
      window.history.replaceState({}, '', '/embed/conversation/token')
      expect(resolveHistoryBase()).toBe('/')
    })
  })

  describe('embedApiPrefix', () => {
    it('prefixes API paths with the host mount prefix', () => {
      window.history.replaceState({}, '', '/agentteams/embed/conversation/token')
      expect(embedApiPrefix()).toBe('/agentteams')
    })

    it('returns an empty prefix for standalone deployment', () => {
      window.history.replaceState({}, '', '/embed/conversation/token')
      expect(embedApiPrefix()).toBe('')
    })
  })
})
