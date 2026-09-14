# 多阶段构建：先构建管理后台，再由 nginx 托管静态资源并反代后端
FROM node:20-alpine AS admin-build
WORKDIR /app
COPY frontend/admin/package*.json ./
RUN npm install --registry=https://registry.npmmirror.com
COPY frontend/admin/ ./
RUN npm run build

FROM nginx:1.25-alpine
COPY deploy/nginx/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=admin-build /app/dist /usr/share/nginx/html/admin
COPY frontend/widget /usr/share/nginx/html/widget
EXPOSE 80
