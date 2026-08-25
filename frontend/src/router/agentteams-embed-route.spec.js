import { describe, expect, it } from 'vitest'
import router from './index'

describe('Agent Teams embed route', () => {
  it('registers public embed access on the shared conversation component', async () => {
    const route = router.getRoutes().find((item) => item.name === 'AgentTeamsEmbedConversation')
    const standardRoute = router.getRoutes().find((item) => item.name === 'ConversationDisplay')

    expect(route?.path).toBe('/embed/conversation/:token')
    expect(route?.meta.requiresAuth).toBe(false)
    expect(route?.props.default({ params: { token: 'embed-token' } })).toEqual({
      token: 'embed-token',
      accessMode: 'embed'
    })

    const [embedModule, standardModule] = await Promise.all([
      route.components.default(),
      standardRoute.components.default()
    ])
    expect(embedModule.default).toBe(standardModule.default)
  })
})
