// Markdown for private replies and edits, which only the browser can read. Same library and rules as
// the server (maf/markdown.py): no raw HTML, images or headings; single line breaks stay; links open in a new tab;
// __text__ is underline.
window.mafMarkdown = (function () {
  if (!window.markdownit) return null;
  const md = window.markdownit("commonmark", { html: false, breaks: true, linkify: true })
    .enable(["strikethrough", "linkify"])
    .disable(["image", "heading", "lheading", "html_block", "html_inline"]);
  md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
    tokens[idx].attrSet("target", "_blank");
    tokens[idx].attrSet("rel", "nofollow noopener noreferrer");
    return self.renderToken(tokens, idx, options);
  };
  // __text__ is underline (as in chat apps), so bold is **text** only. Same as the server.
  for (const side of ["open", "close"]) {
    md.renderer.rules[`strong_${side}`] = (tokens, idx, options, env, self) =>
      tokens[idx].markup === "__" ? (side === "open" ? "<u>" : "</u>") : self.renderToken(tokens, idx, options);
  }
  const escapeHtml = md.utils.escapeHtml;
  // A label ("Edit #2:") goes at the start of the first paragraph, as on the server.
  return function render(text, label) {
    const html = md.render(text || "");
    if (!label) return html;
    if (html.startsWith("<p>")) return `<p>${escapeHtml(label)} ${html.slice(3)}`;
    return `<p>${escapeHtml(label)}</p>${html}`;
  };
})();
