# Stage 1: build
FROM node:20-alpine AS build
WORKDIR /app
COPY web/package*.json ./
RUN npm ci --prefer-offline
COPY web/ ./
ARG VITE_BASE_PATH=/
ENV VITE_BASE_PATH=${VITE_BASE_PATH}
RUN npm run build

# Stage 2: serve
FROM nginx:alpine
COPY docker/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
