# Theme backgrounds

Six photo themes are defined in `web/js/themes.js`: Forest, Alpine peaks,
Ocean breeze, Woodland light, Mountain lake, and Desert dunes. They currently
use explicit image URLs from Unsplash, with 1920px wallpapers and 420px previews.
Photos are fetched by the browser, not proxied through the mail backend.
Availability and appearance could not be tested in the restricted workspace.

The older eleven scenic presets are CSS artwork and are labelled Illustrated
gradients. Custom photo uploads are supported and stored in browser preferences.

The Unsplash photo identifiers are retained in `PHOTO_THEMES` for provenance.
