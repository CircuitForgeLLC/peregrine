import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ClaimsNotice from './ClaimsNotice.vue'

function make(novelWords: unknown, unusedTerms: unknown) {
  return mount(ClaimsNotice, { props: { novelWords, unusedTerms } as any })
}

describe('ClaimsNotice', () => {
  it('renders nothing when both lists are empty', () => {
    expect(make([], []).html()).toBe('<!--v-if-->')
  })

  it('renders nothing for junk input', () => {
    expect(make(null, 'x').find('section').exists()).toBe(false)
    expect(make(['', '  ', 3], [null]).find('section').exists()).toBe(false)
  })

  it('shows only the new words list when unused is empty', () => {
    const w = make(['kubernetes', 'ansible'], [])
    const lists = w.findAll('ul')
    expect(lists).toHaveLength(1)
    expect(lists[0].findAll('li').map((l) => l.text())).toEqual(['kubernetes', 'ansible'])
    expect(w.text()).toContain('Please check that each one is true for you')
    expect(w.text()).not.toContain('were not used')
  })

  it('shows only the unused terms list when new words is empty', () => {
    const w = make([], ['Terraform'])
    expect(w.findAll('ul')).toHaveLength(1)
    expect(w.text()).toContain('These keywords were not used')
    expect(w.findAll('li').map((l) => l.text())).toEqual(['Terraform'])
  })

  it('has an accessible heading tied to the section', () => {
    const w = make(['x'], [])
    const section = w.find('section')
    const h = w.find('h3')
    expect(section.attributes('aria-labelledby')).toBe(h.attributes('id'))
    expect(h.text()).toBe('A few things to check')
  })

  it('de-duplicates and caps long lists with an and N more sentence', () => {
    const many = Array.from({ length: 25 }, (_, i) => `word${i}`)
    const w = make([...many, 'word0'], [])
    expect(w.findAll('li')).toHaveLength(20)
    expect(w.text()).toContain('and 5 more')
  })

  it('renders terms as text, never html', () => {
    const w = make(['<b>bold</b>'], [])
    expect(w.find('li b').exists()).toBe(false)
    expect(w.find('li').text()).toBe('<b>bold</b>')
  })

  it('uses calm copy with no em dashes, semicolons or urgency', () => {
    const text = make(['a'], ['b']).text()
    expect(text).not.toMatch(/[—;]/)
    expect(text).not.toMatch(/warning|urgent|hurry|immediately|error|wrong|must/i)
  })
})
