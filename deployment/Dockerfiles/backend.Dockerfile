FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY backend/requirements.txt ./requirements.txt
COPY backend/requirements-vm.txt ./requirements-vm.txt
RUN pip install --no-cache-dir -r requirements.txt
ARG INSTALL_LIBVIRT=false
RUN if [ "$INSTALL_LIBVIRT" = "true" ]; then \
      apt-get update \
      && apt-get install -y --no-install-recommends gcc pkg-config libvirt-dev \
      && printf 'libvirt-dev: ' \
      && dpkg-query -W -f='$${Version}\n' libvirt-dev \
      && pip install --no-cache-dir -r requirements-vm.txt \
      && apt-get purge -y gcc pkg-config libvirt-dev \
      && rm -rf /var/lib/apt/lists/*; \
    fi
COPY backend ./
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
