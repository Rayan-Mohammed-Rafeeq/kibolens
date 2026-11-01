FROM node:22-alpine AS build

WORKDIR /app

# Copy dependency manifests, including the committed lockfile
COPY frontend/package.json frontend/package-lock.json ./

# Install exactly the locked dependency versions
RUN npm ci --no-audit --no-fund

# Copy application source
COPY frontend/ ./

# Build production frontend
RUN npm run build

FROM caddy:2.10-alpine

COPY --from=build /app/dist /usr/share/caddy
COPY deployment/Caddyfile /etc/caddy/Caddyfile

EXPOSE 80
