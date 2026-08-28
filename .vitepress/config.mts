import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vitepress'

type SidebarItem = { text: string; link: string }
type SidebarGroup = { text: string; items: SidebarItem[] }

function routeFromMarkdown(path: string): string {
  const cleanPath = path.split('#', 1)[0]
  if (cleanPath === 'README.md') return '/'
  return `/${cleanPath.replace(/\.md$/, '')}`
}

function sidebarFromSummary(): SidebarGroup[] {
  const summaryPath = fileURLToPath(new URL('../SUMMARY.md', import.meta.url))
  const lines = readFileSync(summaryPath, 'utf8').split(/\r?\n/)
  const groups: SidebarGroup[] = []
  let current: SidebarGroup = { text: '开始阅读', items: [] }

  for (const line of lines) {
    const heading = line.match(/^##\s+(.+)$/)
    if (heading) {
      if (current.items.length > 0) groups.push(current)
      current = { text: heading[1], items: [] }
      continue
    }

    const link = line.match(/^\*\s+\[([^\]]+)\]\(([^)]+\.md)(?:#[^)]+)?\)$/)
    if (link) {
      current.items.push({ text: link[1], link: routeFromMarkdown(link[2]) })
    }
  }

  if (current.items.length > 0) groups.push(current)
  return groups
}

export default defineConfig({
  lang: 'zh-CN',
  title: 'Android 自定义控件进阶',
  description: '从 View 原理、Canvas、手势到性能、无障碍与 Compose 互操作',
  base: process.env.GITHUB_ACTIONS === 'true' ? '/android-custom-view-mastery/' : '/',
  appearance: false,
  cleanUrls: true,
  outDir: 'dist',
  vite: {
    build: {
      // The local full-text index for this 58-page book is expected to be ~808 KB.
      chunkSizeWarningLimit: 900,
    },
  },
  srcExclude: [
    '**/dist/**',
    '**/node_modules/**',
    '**/templates/**',
    'SUMMARY.md',
  ],
  themeConfig: {
    siteTitle: 'Android 自定义控件进阶',
    nav: [{ text: '开始阅读', link: '/' }],
    sidebar: sidebarFromSummary(),
    outline: { level: [2, 3], label: '本章目录' },
    search: { provider: 'local' },
    docFooter: { prev: '上一章', next: '下一章' },
    returnToTopLabel: '回到顶部',
    sidebarMenuLabel: '目录',
    darkModeSwitchLabel: '主题',
  },
})
