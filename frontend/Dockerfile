# syntax=docker/dockerfile:1.7

FROM node:24-bookworm-slim AS build

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend ./
RUN npm run build

FROM nginx:1.29-alpine AS runtime

ARG RETOS_VERSION=local
ARG RETOS_REVISION=unknown
ARG RETOS_CREATED=unknown

LABEL org.opencontainers.image.title="RetOS Web" \
      org.opencontainers.image.description="React operational console for RetOS" \
      org.opencontainers.image.source="https://github.com/nfernandezsanz/retOS" \
      org.opencontainers.image.url="https://github.com/nfernandezsanz/retOS" \
      org.opencontainers.image.documentation="https://github.com/nfernandezsanz/retOS/blob/main/docs/docker.md" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${RETOS_VERSION}" \
      org.opencontainers.image.revision="${RETOS_REVISION}" \
      org.opencontainers.image.created="${RETOS_CREATED}"

COPY infra/docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/frontend/dist /usr/share/nginx/html
RUN touch /var/run/nginx.pid \
    && chown -R nginx:nginx \
      /etc/nginx/conf.d \
      /usr/share/nginx/html \
      /var/cache/nginx \
      /var/log/nginx \
      /var/run/nginx.pid

USER nginx
EXPOSE 8080
