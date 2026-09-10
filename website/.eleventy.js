module.exports = function (eleventyConfig) {
  eleventyConfig.addPassthroughCopy("src/images");

  // PostHog web analytics (anonymous, cookieless). The snippet is only
  // rendered when POSTHOG_KEY is set at build time, so local dev builds
  // ship no analytics.
  eleventyConfig.addGlobalData("posthogKey", process.env.POSTHOG_KEY || "");
  eleventyConfig.addGlobalData(
    "posthogHost",
    process.env.POSTHOG_HOST || "https://eu.i.posthog.com"
  );

  return {
    dir: {
      input: "src",
      output: "_site",
      includes: "_includes",
    },
  };
};
