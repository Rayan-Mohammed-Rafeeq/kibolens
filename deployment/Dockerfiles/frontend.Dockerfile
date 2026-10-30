FROM node:22-alpine AS build
WORKDIR /app
COPY frontend/package.json ./
RUN npm install
COPY frontend ./
RUN npm run build

FROM caddy:2.10-alpine
COPY --from=build /app/dist /usr/share/caddy
COPY deployment/Caddyfile /etc/caddy/Caddyfile
EXPOSE 80
