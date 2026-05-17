# Multi-stage build: usa node:20-alpine. Output "standalone" cabe em ~150MB.
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

FROM node:20-alpine AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
# Next.js inlinha NEXT_PUBLIC_* no momento do BUILD (nao em runtime).
# Estes ARGs sao injetados pelo docker-compose via build.args.
# Sem isso, a UI chamaria localhost (fallback) em prod.
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_ANALYTICS_URL
ARG NEXT_PUBLIC_SONAR_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_ANALYTICS_URL=$NEXT_PUBLIC_ANALYTICS_URL \
    NEXT_PUBLIC_SONAR_URL=$NEXT_PUBLIC_SONAR_URL
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
RUN addgroup -S nodejs && adduser -S nextjs -G nodejs
# Apenas o necessario do build standalone
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
ENV PORT=3000 HOSTNAME=0.0.0.0
CMD ["node", "server.js"]
