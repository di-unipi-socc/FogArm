# Stage 1 - build
FROM node:lts-alpine as builder
WORKDIR /usr/src/app
COPY package*.json ./
RUN npm install -g npm@8.11.0
RUN npm update
RUN npm install
COPY . ./
RUN npm run build

EXPOSE 3001

ENTRYPOINT ["npm", "run", "start"]
