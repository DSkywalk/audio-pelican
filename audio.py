# _*_ coding: utf-8 _*_

import os, sys, re, datetime
from os import path, makedirs
from mutagen import File
from PIL import Image
import cStringIO
from shutil import copy2

from logging import info

from pelican import signals
from pelican.readers import BaseReader
from markdown import Markdown

from internetarchive import upload, get_item
from audio_feed import create_feed, write_feed, Enclosure

TAGS = {
    'TITULO': 'TIT2',
    'FECHA': 'TCOP',
    'TAGS': 'TIT1',
    'AUTORES': 'TPE1',
    'TEXTO': 'COMM',
    'TIPO': 'TALB',
    'IMG': 'APIC',
    'ID': 'TGID',
}

PATH_AUDIO = 'audios'
PATH_EMBED = 'embed'
PATH_IMGS = 'imgs'
AUDIO_URL = 'podcast'

S3ACC = 'S3ACC'
S3KEY = 'S3KEY'

class podcast_reader(object):
    """ Simple podcast MP3 audio reader """

    audio_picture = None
    audio_date = None
    audio_id = None

    image_file = None
    image_fullpath = None
    image_data = None

    title = 'foo'
    type = 'bar'

    def __init__(self, file_path, output_path):
        self._path = file_path
        self._output = output_path
        self.audio_data = File(file_path)
        self.duration = int(self.audio_data.info.length / 60)
        self._load_internal_data()

    def get_tags(self, tag):
        return self._get_list(self.audio_data.tags.getall(TAGS[tag])[0])

    def text(self):
        return str(self._tag('TEXTO')[0]).decode('utf-8')

    def _image(self):
        # looking for 'APIC:xxxx.ext'
        for tag in self.audio_data.keys():
            if 'APIC:' in tag:
                self.audio_picture = self.audio_data[tag]

        image_ext = ".%s" % (self.audio_picture.mime).split("/")[1]
        self.image_file = path.join(PATH_AUDIO, PATH_IMGS, path.basename(self._path).replace('.mp3', image_ext))
        self.image_fullpath = path.join(self._output, PATH_AUDIO, PATH_IMGS)
        self.image_data = self.audio_picture.data

    def _title(self):
        self.title = str(self._tag('TITULO')[0]).decode('utf-8')
        self.title_safe = self._safe_me(self.title)

    def _date(self):
        date = str(self._tag('FECHA')[0])
        self.audio_date = datetime.datetime.strptime(date, "%Y-%m-%d")

    # generate global id - to identify the file (unique_id)
    def _id(self):
        # if the user generate an ID, just use it
        if self._tag('ID'):
            self.audio_id = str(self._tag('ID')[0])

        # we use date and safe version of title string
        else:
            self.audio_id = self.audio_date.strftime("%d%m%Y_")
            self.audio_id += self.title_safe

    def _type(self):
        self.type = str(self._tag('TIPO')[0]).decode('utf-8')
        self.type_safe = self._safe_me(self.type)

    def _safe_me(self, name):
        regex = re.compile("[^\w\-]")
        return regex.sub(
            "",
            name.replace(" ", "_").lower()
        )

    def _tag(self, audio_tag):
        return self.audio_data.tags.getall(TAGS[audio_tag])

    def _get_list(self, audio_tag):
        return [x.strip() for x in str(audio_tag).decode('utf-8').split(",")]

    def _load_internal_data(self):
        self._image()
        self._title()
        self._date()
        self._id()
        self._type()


class audio_reader(BaseReader):
    """ Pelican audio Reader """

    enabled = True
    file_extensions = ['mp3']

    def read(self, file_path):
        S3ACC = self.settings.get('S3ACC')
        S3KEY = self.settings.get('S3KEY')
        content_path = self.settings.get("PATH", "content")
        output_path = self.settings.get("OUTPUT_PATH", "output")

        pd = podcast_reader(file_path, output_path)

        metadata = {
            'title': pd.title,
            'category': AUDIO_URL,
            'tags': pd.get_tags('TAGS'),
            'authors': pd.get_tags('AUTORES'),
            'date': pd.audio_date.isoformat(),
            'audio': 'https://archive.org/download/%s/%s' % (pd.audio_id, path.basename(file_path)),
            'audio_id': pd.audio_id,
            'embed': path.join(PATH_AUDIO, PATH_EMBED, path.basename(file_path).replace('.mp3', '.html')),
            'image': pd.image_file,
            'duration': pd.duration,
            'size': os.stat(file_path).st_size,
            'type': pd.type,
            'type_safe': pd.type_safe,
            'template': 'audio',
        }

        texto = pd.text()

        md = dict(
            language = 'spa',
            mediatype = 'audio',
            noindex = 'noindex',
            collection = 'test_collection', # 'opensource_audio'
            title = metadata['title'],
            description = texto,
            subject = metadata['tags'],
            date = metadata['date'],
        )

        #info('MP3-IMG writing {0}'.format(pd.image_file))
        try:
            makedirs(pd.image_fullpath)
        except:
            pass

        self._save_image(pd.image_data, path.join(output_path, pd.image_file))

        archive_data = get_item(pd.audio_id)
        if not archive_data.item_size:
            response = upload(
                pd.audio_id,
                files=[path.join(output_path, image_file), file_path],
                metadata=md,
                verbose=True,
                verify=True,
                retries=3,
                retries_sleep=3600,
                access_key=S3ACC,
                secret_key=S3KEY
            )

            info("NEW URL: https://archive.org/details/%s" % pd.audio_id)
            info("upload response:", response)
        else:
            info("CUR URL: https://archive.org/details/%s" % pd.audio_id)

        parsed = {}
        for key, value in metadata.items():
            parsed[key] = self.process_metadata(key, value)

        # parse Markdown text
        self._md = Markdown(extensions=self.settings['MARKDOWN']['extensions'])
        content = self._md.convert(texto)
        return content, parsed

    def _save_image(self, oData, sPath):
        basewidth = 500
        img = Image.open(cStringIO.StringIO(oData))
        height = self._get_hsize(img, basewidth)
        img = img.resize((basewidth, height), Image.ANTIALIAS)
        img.save(sPath)

    def _get_hsize(self, img, width):
        wpercent = (width/float(img.size[0]))
        return int((float(img.size[1])*float(wpercent)))


def generate_embed_pages(generator, writer):
    """ Generate iFrame-Player , called after write all html articles """

    embed_first = False
    for article in generator.articles:
        if 'audio' in article.metadata.keys():
            template = generator.get_template('audio_embed')
            save_as = article.metadata['embed']
            page = {'mainurl': article.url,}
            metadata = article.metadata

            writer.write_file(
                save_as, template, generator.context,
                generator.settings['RELATIVE_URLS'],
                override_output=True, page=page, meta=metadata
            )

            if not embed_first:
                embed_first = True
                writer.write_file(path.join(PATH_AUDIO, PATH_EMBED,"home.html"), template, generator.context,
                              generator.settings['RELATIVE_URLS'], override_output=True, page=page, meta=metadata)


def generate_rss_audio(generator, writer):
    """ Generate rss audio, called after write all html articles """

    feeds_by_type = {}
    feed = create_feed(generator.settings)

    for article in generator.articles:
        if 'audio' in article.metadata.keys():
            e = Enclosure(article.audio, str(article.size), u'audio/mpeg')

            feed.add_item(
                title=article.title,
                link="http://rigorycriterio.es/" + article.url,
                description=article.content,
                duration=article.duration,
                pubdate=article.date,
                enclosure=e,
                thumb="http://rigorycriterio.es/" + article.image,
                unique_id=article.metadata['audio_id']
            )

            if article.type_safe not in feeds_by_type.keys():
                feeds_by_type[article.type_safe] = create_feed(generator.settings, article.type)

            feeds_by_type[article.type_safe].add_item(
                title=article.title,
                link="http://rigorycriterio.es/" + article.url,
                description=article.content,
                duration=article.duration,
                pubdate=article.date,
                enclosure=e,
                thumb="http://rigorycriterio.es/" + article.image,
                unique_id=article.metadata['audio_id']
            )

    write_feed(generator.settings, feed)

    for type, feed in feeds_by_type.iteritems():
        write_feed(generator.settings, feed, type)


def add_reader(readers):
    """ Add new file type reader to pelican """

    readers.reader_classes['mp3'] = audio_reader


def register():
    """ Pelican plugin connector """

    signals.article_writer_finalized.connect(generate_embed_pages)
    signals.article_writer_finalized.connect(generate_rss_audio)
    signals.readers_init.connect(add_reader)
