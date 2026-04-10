# pi-harness/Dockerfile
# Node 22 LTS — locked decision per CONTEXT.md (pi-mono requires >=20.6.0; 22 is active LTS until April 2027)
FROM node:22-alpine

# curl for Compose healthcheck
RUN apk add --no-cache curl

WORKDIR /app

# Install all deps (including devDeps for tsc)
COPY package*.json ./
RUN npm ci

# Compile TypeScript → CommonJS in dist/
COPY tsconfig.json ./
COPY src/ ./src/
RUN npm run build

# Drop dev deps (typescript, @types) after compile
RUN npm prune --omit=dev

# CRITICAL: Add node_modules/.bin to PATH so 'pi' binary is found by spawn()
ENV PATH="/app/node_modules/.bin:$PATH"

# Entrypoint writes ~/.pi/agent/models.json from env vars at container start
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 3000
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["node", "dist/bridge.js"]
