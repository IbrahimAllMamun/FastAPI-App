# ---- Build stage ----
# Node 20 on Alpine as a temporary build environment, named "build"
FROM node:20-alpine AS build
# all following instructions in this stage run from /app
WORKDIR /app

# copy package.json + package-lock.json first, so dependency install caches separately from source
COPY package*.json ./
# clean, reproducible install based exactly on package-lock.json
RUN npm ci

# copy the rest of the frontend source code into the build stage
COPY . .
# build-time argument, overridable via docker-compose's build.args
ARG VITE_API_URL=/api
# expose it as an env var so Vite picks it up and bakes it into the compiled JS
ENV VITE_API_URL=$VITE_API_URL
# run Vite's production build, producing static files in /app/dist
RUN npm run build

# ---- Serve stage ----
# fresh, much smaller image — just nginx, no Node toolchain
FROM nginx:1.27-alpine
# copy only the compiled static files from the build stage above
COPY --from=build /app/dist /usr/share/nginx/html
# replace nginx's default site config with our own
COPY nginx.conf /etc/nginx/conf.d/default.conf

# documents that this container serves HTTP on port 80
EXPOSE 80
# run nginx in the foreground so the container keeps running
CMD ["nginx", "-g", "daemon off;"]
