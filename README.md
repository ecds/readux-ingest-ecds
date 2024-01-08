# readux-ingest-ecds

Django app for Readux ingest specific to ECDS' infrastructure

## Install

bash~~~
pip ...
~~~

### Make and run migrations

bash~~~
python manage.py makemigrations readux_ingest_ecds
python manage.py migrate
~~~

## Settings

- IIIF_APPS
- INGEST_TMP_DIR
- INGEST_PROCESSING_DIR
- INGEST_OCR_DIR
