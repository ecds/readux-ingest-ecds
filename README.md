# Readux Ingest ECDS

Django app for Readux ingest specific to ECDS' infrastructure.

1. [Install](#install)
2. [Settings](#settings)
3. [Process](#process)
    1. [Local Ingest](#local-ingest)
    2. [Bulk Ingest](#bulk-ingest)
    3. [Remote Ingest](#remote-ingest)

## Install

~~~bash
pip install git+https://github.com/ecds/readux-ingest-ecds@develop
~~~

Add readux_ingest_ecds to the INSTALLED_APPS in config/settings/local.py

~~~python
INSTALLED_APPS += ['readux_ingest_ecds']
~~~

Create and run the migrations.

~~~bash
python manage.py migrate readux_ingest_ecds
~~~

## Settings

**NOTE:** All values are simple strings.
| Setting | Value|
|---------|-------|
| IIIF_MANIFEST_MODEL | Model reference, eg. 'iiif.Manifest' |
| IIIF_IMAGE_SERVER_MODEL | Model reference, eg. 'iiif.ImageServer' |
| IIIF_RELATED_LINK_MODEL | Model reference, eg. 'iiif.RelatedLink' |
| IIIF_CANVAS_MODEL | Model reference, eg. 'iiif.Canvas' |
| IIIF_COLLECTION_MODEL | Model reference, eg. 'iiif.Collection' |
| INGEST_TMP_DIR | Absolute path where files will be temporarily stored. |
| INGEST_PROCESSING_DIR | Absolute path where Lambda will look for images. |
| INGEST_OCR_DIR | Absolute path where OCR files will be preserved. |
| INGEST_TRIGGER_BUCKET | S3 bucket that will trigger the PTiff Lambda function. |

## Process

### Local Ingest

A person uploads a zip file with the following internal structure.

~~~bash
.
├──
│   └── metadata.(csv|tsv|xlsx)
│   └── images
│   │   └── 0000X.(tiff|jpg|png|gif|webp)
│   └── ocr
│   │   └── 0000X.(txt|tsv|xml|hocr)
~~~

#### Image Files

The "images" directory should contain all images sequentially named with numbers. Images can be in any format (other than PDF). Non-pyramidal tiffs will be converted during the ingest process.

#### OCR Files

OCR files file names should match its corresponding image. Readux currently supports hocr, Alto, and tab delimited (tsv).

#### Metadata File

The optional metadata file should be a spreadsheet. CSV is best, but TSV and Excel files are supported. The table below lists the supported column headers.

| Header | Description |
|--------|-------------|
| PID    | **UNIQUE** identifier. If it is missing, Readux will assign one. |
| Label | Volume Title, if the title is extremely long, you can abbreviate it and put the rest into the Summary. |
| Summary | All descriptive information, you can use html &lt;br/&gt; to automatically add line breaks into the text. |
| Author | Last name, First name, dates; separate multiple authors by semi-colon. |
| Published city | City from publisher information. |
| Published date | Date of publication. |
| Published date edtf | Date of publication in [extended date time format](https://www.loc.gov/standards/datetime/) for search. Year can be the same (1688 = 1688) but a range changes (1688-1690 = 1688/1690). |
| Publisher | Publisher from publisher information. |
| PDF | Link to a file if available (optional). |
| Scanned by | Usually "Emory Libraries" |
| Identifier | The Library Call Number. |
| Identifier uri | Link to the item in the Library database. |

#### How It Works

When the zip file is uploaded, the metadata file will be read, a new manifest/volume will be created. A background job will start unpacking all the image and OCR files and the person will be redirected to the edit form for the new manifest.

The background job will save teh OCR files and save all the image files in a staging directory. While the image files are being unpacked, each file name is added to a text file. That text file is uploaded to a specific S3 bucket. When the file is saved to the S3 bucket, an AWS Lambda function will convert each file in the list to a ptiff and save it in the image directory for the IIP server.

### Bulk Ingest

Coming soon...

### Remote Ingest

Coming soon...
