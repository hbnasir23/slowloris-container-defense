FROM httpd:2.4

# A small, realistic web app plus an intentionally small worker pool so the
# connection-exhaustion effect of Slowloris is observable in minutes, not hours.
COPY httpd.conf /usr/local/apache2/conf/httpd.conf
RUN mkdir -p /usr/local/apache2/htdocs \
 && printf '<!doctype html><title>Lab service</title><h1>OK</h1>' \
    > /usr/local/apache2/htdocs/index.html

HEALTHCHECK --interval=5s --timeout=2s --retries=3 \
  CMD curl -fs http://127.0.0.1:80/ >/dev/null || exit 1

EXPOSE 80
