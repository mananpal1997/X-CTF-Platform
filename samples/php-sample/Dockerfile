FROM php:8.2-apache

# Accept build arguments
ARG FLAG_VALUE
ARG CHALLENGE_NAME

# Set environment variables (accessible at runtime)
ENV FLAG_VALUE=${FLAG_VALUE}
ENV CHALLENGE_NAME=${CHALLENGE_NAME}

# Set working directory
WORKDIR /var/www/html

# Install required extensions if needed
# RUN docker-php-ext-install mysqli pdo pdo_mysql

# Copy challenge files
COPY challenge/ /var/www/html/

# Set permissions
RUN chown -R www-data:www-data /var/www/html && \
    chmod -R 755 /var/www/html

# Configure Apache to listen on port 8000
RUN sed -i 's/Listen 80/Listen 8000/' /etc/apache2/ports.conf && \
    sed -i 's/<VirtualHost \*:80>/<VirtualHost *:8000>/' /etc/apache2/sites-available/000-default.conf

# Expose port 8000 (required by X-CTF platform)
EXPOSE 8000

# Start Apache
CMD ["apache2-foreground"]

