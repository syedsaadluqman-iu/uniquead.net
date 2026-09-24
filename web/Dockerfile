# Base image for Odoo 18
FROM odoo:18.0

# Switch to root during image build
USER root

# Copy Python dependency file
COPY web/requirements.txt /requirements.txt

# Install dependencies system-wide
RUN pip install --no-cache-dir --break-system-packages \
    -r /requirements.txt