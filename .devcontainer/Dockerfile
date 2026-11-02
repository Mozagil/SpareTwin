# Geliştirme ortamı: Python 3.12 + Node 22 (frontend için).
# Node, resmi Node imajından kopyalanır; ek eklenti (feature) gerekmez.
FROM node:22-bookworm-slim AS node

FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -sf /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -sf /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
 && node --version && npm --version
