# Claude Chat Frontend - Vue3 Application
FROM node:24-alpine AS build-stage

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY package*.json ./

# 安装依赖（使用淘宝镜像）
RUN npm config set registry https://registry.npmmirror.com && npm ci

# 复制应用代码
COPY . .

# 构建应用
RUN npm run build

# 生产阶段
FROM nginx:alpine AS production-stage

ENV AGENTTEAMS_EMBED_FRAME_ANCESTORS="'self'"

# 复制构建产物
COPY --from=build-stage /app/dist /usr/share/nginx/html

# 官方 nginx entrypoint 会在启动时将允许嵌入的来源写入最终配置。
COPY nginx.conf /etc/nginx/templates/default.conf.template

# 暴露端口
EXPOSE 80

# 启动 nginx
CMD ["nginx", "-g", "daemon off;"]
