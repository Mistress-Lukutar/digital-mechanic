import { marked } from 'marked'
import DOMPurify from 'dompurify'

marked.setOptions({ gfm: true, breaks: true })

DOMPurify.addHook('afterSanitizeAttributes', function (node) {
  if (node.hasAttribute('href')) {
    node.setAttribute('target', '_blank')
    node.setAttribute('rel', 'noopener noreferrer')
  }
})

function escapeHtml(str: string): string {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;')
}

export function renderMarkdown(source: string): string {
  const html = marked.parse(source, { async: false }) as string
  return DOMPurify.sanitize(html)
}

export function renderAssistantHtml(source: string): string {
  // Unwrap backtick-wrapped citations before markdown rendering
  source = source.replace(/`([^\n`]*, стр\. \d+\])/g, '$1')
  const html = renderMarkdown(source)
  const citationRegex = /\[([^<>,\[\]]+), стр\. (\d+)\]/g
  const result = html.replace(citationRegex, (_match, docId, page) => {
    const cleanDocId = docId.replace(/[«»]/g, '').trim()
    return '<a href="#" class="citation-link" data-doc-id="' + escapeHtml(cleanDocId) + '" data-page="' + page + '">' + '[' + escapeHtml(cleanDocId) + ', стр. ' + page + ']</a>'
  })
  return result
}
