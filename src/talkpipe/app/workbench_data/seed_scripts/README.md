# Seed scripts for workbench suggestions

Hand-synced copies of `docs/tutorials/**/*.script` (docs/ is not shipped in
wheels). They are mined at workbench startup — together with the built-in
examples and the user's saved pipelines — to build the co-occurrence tables
behind the "Likely next" suggestions and autocomplete ranking.

When a tutorial script changes, refresh their copy here (the filename encodes
the original path).
