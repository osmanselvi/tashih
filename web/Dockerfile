# --- Frontend derleme ---
FROM node:22-alpine AS build

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
RUN npm run build

# --- Apache (httpd) ile sunum ---
FROM httpd:2.4-alpine

# mod_proxy modüllerini etkinleştir ve vhost'u dahil et
RUN sed -ri \
      -e 's!^#(LoadModule proxy_module modules/mod_proxy\.so.*)!\1!' \
      -e 's!^#(LoadModule proxy_http_module modules/mod_proxy_http\.so.*)!\1!' \
      /usr/local/apache2/conf/httpd.conf \
    && printf '\nInclude conf/extra/tashih.conf\n' >> /usr/local/apache2/conf/httpd.conf

# Vhost: konteyner içi yollar ve backend adresi ("api" servisi)
COPY apache/tashih.conf /usr/local/apache2/conf/extra/tashih.conf
RUN sed -ri \
      -e 's!^DocumentRoot .*!DocumentRoot /usr/local/apache2/htdocs!' \
      -e 's!<Directory [^>]*>!<Directory /usr/local/apache2/htdocs>!' \
      -e 's!http://127\.0\.0\.1:8000!http://api:8000!g' \
      /usr/local/apache2/conf/extra/tashih.conf

COPY --from=build /app/dist /usr/local/apache2/htdocs/
EXPOSE 80
