# Production image — Next.js frontend
FROM node:20-alpine

WORKDIR /app

# Proxy /api rewrites at build time (next.config resolves backend URL when config loads)
ARG API_PROXY_TARGET=http://backend:8000
ENV API_PROXY_TARGET=${API_PROXY_TARGET}

ARG NEXT_PUBLIC_API_KEY=dev-local-key
ENV NEXT_PUBLIC_API_KEY=${NEXT_PUBLIC_API_KEY}

COPY package.json package-lock.json ./
RUN npm ci --legacy-peer-deps

COPY . .

RUN npm run build

ENV NODE_ENV=production

EXPOSE 3000

CMD ["npx", "next", "start", "-H", "0.0.0.0", "-p", "3000"]
