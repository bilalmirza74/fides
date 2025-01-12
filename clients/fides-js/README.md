# fides-js

## Overview

`fides-js` is a typescript package and library to handle rendering a Fides overlay on top of an existing website. An overlay is defined as both the banner and the modal that show up when asking a user to agree to cookies, notices, etc.

Currently, there are two libraries that `fides-js` can build:

1. `fides.js` which can serve privacy notices
2. `fides-tcf.js` which can serve TCF

Since `fides-js` is just a package/library, it needs to be hosted somewhere in order to access it. We use the `privacy-center`[../privacy-center]'s `/api/fides-js` endpoint to do so.

## Developing

You will need certain environment variables:

```sh
# for debugging
FIDES_PRIVACY_CENTER__DEBUG=true

# Necessary for notices or TCF. `false` would use legacy consent (from config.json)
FIDES_PRIVACY_CENTER__IS_OVERLAY_ENABLED=true

# Necessary for TCF, optional for notices
FIDES_PRIVACY_CENTER__IS_PREFETCH_ENABLED=true

# Necessary if prefetch is not enabled
FIDES_PRIVACY_CENTER__IS_GEOLOCATION_ENABLED=true
FIDES_PRIVACY_CENTER__GEOLOCATION_API_URL=https://cdn-api.ethyca.com/location
```

You can put these in an `.env` file. The location of your `.env` file depends on how you want to run `fides-js`.

### From a development privacy center

Typically, you will want to make your changes within `fides-js`, then run `turbo dev` in the `privacy-center`[../privacy-center] directory. In this case, you want your `.env` file at the root of the privacy-center folder. Because of how we have `turbo` configured, the privacy center will build the latest in `fides-js`, then use it directly within its app. However, because it is built and then pulled into the privacy center, this means that hot reloading does not work, so you will have to stop and restart your `turbo dev` each time you make a change in `fides-js`.

Once you have the privacy center running, you can view `fides-js` in action at our demo page, located at `[privacy-center-host]:[port]/fides-js-demo.html`. This is an HTML page with helpful information about how `fides-js` is configured, and will itself load `fides-js`.

### From a full test environment

Alternatively, you may want to run the entire test environment. This is particularly useful if you want to test `fides-js` on a site that looks more "real" such as our sample-app. In this case, you want your `.env` file at the root of the `fides` repo.

Once you have your environment variables set up, you can run `nox -s "fides_env(test)"` and the sample app should have `fides-js` loaded.

It can be useful to take down individual containers in the full environment if you want to iterate on `fides-js` at the same time (for instance, to take down the privacy center container in favor of your own development instance of the privacy center).
