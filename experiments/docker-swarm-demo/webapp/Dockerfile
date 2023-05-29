FROM node:lts-alpine as build-stage
WORKDIR /app
COPY package*.json ./
RUN npm install -g npm@8.11.0
RUN npm update
RUN npm install
COPY ./ .
RUN npm run build

FROM nginx as production-stage
RUN mkdir /app
COPY --from=build-stage /app/dist /app
COPY nginx.conf /etc/nginx/nginx.conf
