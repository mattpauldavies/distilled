// Applies to every template in src/docs/. Tagging and permalinks live here so
// that adding a documentation page means adding one file: the `docs` tag puts
// it in the sidebar collection, and the permalink keeps the flat .html output
// the Caddy URL contract expects (see website/README.md).
module.exports = {
  tags: ["docs"],
  permalink: "/docs/{{ page.fileSlug }}.html",
};
