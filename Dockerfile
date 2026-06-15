FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# Pillow (ImageField) needs JPEG/zlib; gosu drops root after fixing volume permissions.
RUN apt-get update \
	&& apt-get install -y --no-install-recommends libjpeg62-turbo-dev zlib1g-dev gosu \
	&& rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip \
	&& pip install --no-cache-dir -r requirements.txt

RUN groupadd --system appuser \
	&& useradd --system --gid appuser --create-home appuser

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN sed -i 's/\r$//' /docker-entrypoint.sh \
	&& chmod +x /docker-entrypoint.sh \
	&& chown -R appuser:appuser /app

COPY . /app
RUN chown -R appuser:appuser /app

# Entrypoint runs as root to chown mounted volumes, then gosu → appuser.
USER root
ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
