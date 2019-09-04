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


TAGS = {    'TITULO': 'TIT2',
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

def get_content_path(pelican):
    return pelican.settings.get('PATH')


def get_audio_path(pelican):
    audio_path = pelican.settings.get('AUDIO_PATH', 'audio')
    content_path = get_content_path(pelican)

    return os.path.join(content_path, audio_path)


def get_list(pStr):
    return [ x.strip() for x in str(pStr).decode('utf-8').split(",") ]

def get_hsize(img, width):
    wpercent = (width/float(img.size[0]))
    return int((float(img.size[1])*float(wpercent)))

def save_image(oData, sPath):
    basewidth = 500
    img = Image.open(cStringIO.StringIO(oData))
    height = get_hsize(img, basewidth)
    img = img.resize((basewidth, height), Image.ANTIALIAS)
    img.save(sPath)

class audio_reader(BaseReader):
    enabled = True
    file_extensions = ['mp3']

    def read(self, sFilepath):
        S3ACC = self.settings.get('S3ACC')
        S3KEY = self.settings.get('S3KEY')
        content_path = self.settings.get("PATH", "content")
        output_path = self.settings.get("OUTPUT_PATH", "output")
        aud = File(sFilepath)
        regex = re.compile("[^\w\-]")

        aPIC = None
        audio_id = None
        for aInfo in aud.keys():
            if 'APIC:' in aInfo:
                aPIC = aud[aInfo]
        imgExt = ".%s" % (aPIC.mime).split("/")[1]
        imgFile = path.join(PATH_AUDIO, PATH_IMGS, path.basename(sFilepath).replace('.mp3', imgExt))
        imgPath = path.join(output_path, PATH_AUDIO, PATH_IMGS)
        imgData = aPIC.data

        title = str(aud.tags.getall(TAGS['TITULO'])[0]).decode('utf-8')
        date = str(aud.tags.getall(TAGS['FECHA'])[0])
        ddate = datetime.datetime.strptime(date, "%Y-%m-%d")
        # generamos el id - global del podcast que lo identifica de forma unica
        # si usamos el tag - Identificador de Podcast - no generamos nada...
        if aud.tags.getall(TAGS['ID']):
            audio_id = str(aud.tags.getall(TAGS['ID'])[0])
        else:
            audio_id = ddate.strftime("%d%m%Y_")
            audio_id += regex.sub("", title.replace(" ", "_").lower())

        metadata = {'title': title,
                    'category': AUDIO_URL,
                    'tags': get_list(aud.tags.getall(TAGS['TAGS'])[0]),
                    'authors': get_list(aud.tags.getall(TAGS['AUTORES'])[0]),
                    'date': ddate.isoformat(),
                    'audio': 'https://archive.org/download/%s/%s' % (audio_id, path.basename(sFilepath)),
                    'audio_id': audio_id,
                    'embed': path.join(PATH_AUDIO, PATH_EMBED, path.basename(sFilepath).replace('.mp3', '.html')),
                    'image': imgFile,
                    'duration': int(aud.info.length / 60),
                    'size': os.stat(sFilepath).st_size,
                    'type': str(aud.tags.getall(TAGS['TIPO'])[0]).decode('utf-8'),
                    'template': 'audio',
                    }

        texto = str(aud.tags.getall(TAGS['TEXTO'])[0]).decode('utf-8')
        parsed = {}

        #outFile = path.join(output_path, metadata['audio'])


        md = dict(
            language = 'spa',
            mediatype = 'audio',
            #noindex = 'noindex',
            collection = 'opensource_audio', # 'test_collection'
            title = metadata['title'],
            description = texto,
            subject = metadata['tags'],
            date = ddate.isoformat()
        )

        #info('MP3-IMG writing {0}'.format(imgFile))
        try:
            makedirs(imgPath)
        except:
            pass

        save_image(imgData, path.join(output_path, imgFile))

        i = get_item(audio_id)
        if not i.item_size:
            response = upload(audio_id, files=[path.join(output_path, imgFile), sFilepath], metadata=md, verbose=True, verify=True, retries=3, retries_sleep=3600, access_key=S3ACC, secret_key=S3KEY)
            #info("NEW URL: https://archive.org/details/%s" % audio_id)
            #info("upload response:", response)
        else:
            #info("CUR URL: https://archive.org/details/%s" % audio_id)
            print "xml size:", i.item_size

        """
        #info('MP3 org {0}'.format(sFilepath))
        info('MP3 writing {0}'.format(outFile))
        try:
            makedirs(path.dirname(outFile))
        except:
            pass
        # save mp3
        copy2(sFilepath, outFile)
        """


        for key, value in metadata.items():
            parsed[key] = self.process_metadata(key, value)

        # parse Markdown text
        self._md = Markdown(extensions=self.settings['MARKDOWN']['extensions'])
        content = self._md.convert(texto)
        return content, parsed

def generate_embed_pages(generator, writer):

    embed_first = False
    for article in generator.articles:
        if 'audio' in article.metadata.keys():
            template = generator.get_template('audio_embed')
            save_as = article.metadata['embed']
            page = {'mainurl': article.url,}
            metadata = article.metadata
            #info('writing_embed {0}'.format(save_as))

            writer.write_file(save_as, template, generator.context,
                              generator.settings['RELATIVE_URLS'], override_output=True, page=page, meta=metadata)
            if not embed_first:
                embed_first = True
                writer.write_file(path.join(PATH_AUDIO, PATH_EMBED,"home.html"), template, generator.context,
                              generator.settings['RELATIVE_URLS'], override_output=True, page=page, meta=metadata)



def generate_rss_audio(generator, writer):
    feed = create_feed(generator.settings)
    for article in generator.articles:
        if 'audio' in article.metadata.keys():
            e = Enclosure(article.audio, str(article.size), u'audio/mpeg')
            feed.add_item(title=article.title,
                          link="http://rigorycriterio.es/" + article.url,
                          description=article.content,
                          duration=article.duration,
                          pubdate=article.date,
                          enclosure=e,
                          thumb="http://rigorycriterio.es/" + article.image,
                          unique_id=article.metadata['audio_id'])

    #info('writing_rss audio.rss.xml')
    write_feed(generator.settings, feed)

def add_reader(readers):
    readers.reader_classes['mp3'] = audio_reader

def register():
    signals.article_writer_finalized.connect(generate_embed_pages)
    signals.article_writer_finalized.connect(generate_rss_audio)
    signals.readers_init.connect(add_reader)
