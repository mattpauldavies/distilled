module.exports = function (eleventyConfig) {
  eleventyConfig.addPassthroughCopy("src/images");

  // Pages are written to flat .html files but linked at their extensionless
  // URL — see the URL contract in website/README.md.
  eleventyConfig.addFilter("canonical", (url) =>
    url.replace(/\/index\.html$/, "/").replace(/\.html$/, "")
  );

  // The documentation sidebar and its previous/next links are rendered from
  // this collection, so adding a page to src/docs/ is the only step needed to
  // put it in the navigation. Order comes from each page's `order` front
  // matter.
  eleventyConfig.addCollection("docs", (collectionApi) =>
    collectionApi
      .getFilteredByTag("docs")
      .sort((a, b) => a.data.order - b.data.order)
  );

  // PostHog web analytics (anonymous, cookieless). The snippet is only
  // rendered when POSTHOG_KEY is set at build time, so local dev builds
  // ship no analytics.
  //
  // Events go through a first-party reverse proxy rather than straight to
  // eu.i.posthog.com, which content blockers and Safari/Firefox tracking
  // protection block outright. posthogUiHost keeps in-app links pointing at
  // PostHog itself rather than at the proxy domain.
  eleventyConfig.addGlobalData("posthogKey", process.env.POSTHOG_KEY || "");
  eleventyConfig.addGlobalData(
    "posthogHost",
    process.env.POSTHOG_HOST || "https://d.distilledmetrics.com"
  );
  eleventyConfig.addGlobalData(
    "posthogUiHost",
    process.env.POSTHOG_UI_HOST || "https://eu.posthog.com"
  );

  return {
    dir: {
      input: "src",
      output: "_site",
      includes: "_includes",
    },
  };
};
