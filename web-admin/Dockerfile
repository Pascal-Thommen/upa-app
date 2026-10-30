FROM nginx:alpine

RUN rm -rf /usr/share/nginx/html/*

COPY web-admin/nginx.conf /etc/nginx/conf.d/default.conf
COPY web-admin/ /usr/share/nginx/html/
COPY web-app/ /usr/share/nginx/html/campus/

RUN ln -s /usr/share/nginx/html /usr/share/nginx/html/dashboard 2>/dev/null || true

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=5s --start-period=3s --retries=3 \
    CMD wget -qO- http://127.0.0.1:80/frontend-health || exit 1

CMD ["nginx", "-g", "daemon off;"]
