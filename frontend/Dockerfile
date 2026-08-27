FROM node:24-slim

WORKDIR /app

COPY package.json pnpm-lock.yaml* ./
RUN corepack enable \
  && corepack prepare pnpm@11.19.0 --activate \
  && pnpm install --frozen-lockfile --ignore-scripts

COPY . .

EXPOSE 3000

CMD ["pnpm", "dev"]
