FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json tsconfig.json ./
RUN npm ci
COPY src/ ./src/
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=8086
ENV HOST=0.0.0.0
ENV TOKEN_SIGNING_SECRET=velora-card-signing-secret-prod-uaen

COPY package*.json ./
RUN npm ci --only=production
COPY --from=builder /app/dist ./dist
COPY src/templates ./dist/templates

EXPOSE 8086
CMD ["node", "dist/index.js"]
