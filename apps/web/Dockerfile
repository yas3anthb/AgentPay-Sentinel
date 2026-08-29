# Multi-stage: the runner carries only the standalone server output.
FROM node:22-alpine AS deps
WORKDIR /app
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY apps/web/ ./
# The audit page reads the real .rego files at request time, so they ship too.
COPY policies/ /policies/
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
# Next's standalone server.js binds to $HOSTNAME if it is set, and Docker sets
# HOSTNAME to the container id by default — which resolves to the container's
# real interface IP, not 0.0.0.0. That leaves `curl localhost:3000` (used by
# the healthcheck, and by anything else inside the container) unable to reach
# a server that is actually running fine. Forcing HOSTNAME=0.0.0.0 is the
# documented fix for this exact interaction.
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN apk add --no-cache curl
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /policies /policies
ENV POLICIES_DIR=/policies
EXPOSE 3000
CMD ["node", "server.js"]
