# syntax=docker/dockerfile:1.7

FROM node:24-bookworm-slim AS build

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend ./
RUN npm run build

FROM nginx:1.29-alpine AS runtime

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
