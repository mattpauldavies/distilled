module.exports = function (eleventyConfig) {
  eleventyConfig.addPassthroughCopy("src/images");

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
