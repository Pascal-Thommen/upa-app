FROM nginx:alpine

# Remove default nginx assets
RUN rm -rf /usr/share/nginx/html/*

# Copy custom nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy web-admin assets to document root
COPY . /usr/share/nginx/html/

# Create symlink for /dashboard directory inside document root
RUN ln -s /usr/share/nginx/html /usr/share/nginx/html/dashboard 2>/dev/null || true

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=5s --start-period=3s --retries=3 \
    CMD wget -qO- http://127.0.0.1:80/frontend-health || exit 1

CMD ["nginx", "-g", "daemon off;"]
