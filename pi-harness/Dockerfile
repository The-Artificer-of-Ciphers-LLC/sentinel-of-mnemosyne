# pi-harness/Dockerfile
# Node 22 LTS — locked decision per CONTEXT.md (pi-mono requires >=20.6.0; 22 is active LTS until April 2027)
FROM node:22-alpine

# curl for Compose healthcheck
RUN apk add --no-cache curl

WORKDIR /app

# Install dependencies first (layer caching)
COPY package*.json ./
RUN npm ci --omit=dev

# CRITICAL: Add node_modules/.bin to PATH so 'pi' binary is found by spawn()
# Without this, spawn('pi', ...) fails with ENOENT even though npm ci installed it
ENV PATH="/app/node_modules/.bin:$PATH"

COPY src/ ./src/
COPY tsconfig.json ./

EXPOSE 3000

# Use --experimental-strip-types to run TypeScript directly in Node 22
# (avoids a compile step in the container; acceptable for this service)
CMD ["node", "--experimental-strip-types", "src/bridge.ts"]
