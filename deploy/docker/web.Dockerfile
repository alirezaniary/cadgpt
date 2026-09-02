# The SPA is built once and served as static files. There is no Node process in
# production: the product is API-only, so the frontend has no server side to run.

FROM node:22-alpine AS build

WORKDIR /app
RUN corepack enable

COPY services/web/package.json services/web/pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile || pnpm install

COPY services/web .
ARG VITE_API_URL=/api
ENV VITE_API_URL=$VITE_API_URL
RUN pnpm run build

FROM nginx:1.27-alpine AS runtime
COPY --from=build /app/dist /usr/share/nginx/html
COPY deploy/docker/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
