FROM node:20-alpine AS builder

WORKDIR /app
ARG NEXT_PUBLIC_API_BASE
ARG NEXT_PUBLIC_WS_BASE
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE
ENV NEXT_PUBLIC_WS_BASE=$NEXT_PUBLIC_WS_BASE
COPY package*.json ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
COPY . .
RUN npm run build

FROM node:20-alpine

WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
