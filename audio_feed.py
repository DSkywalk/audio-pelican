# _*_ coding: utf-8 _*_

import os
from feedgenerator import Rss201rev2Feed, Enclosure

TITLE = "Rigor y Criterio | No tienes ni idea..."
SUBTITLE = u"Cine, Television, Comic, Literatura, Videojuegos y Cultura Pop"
AUTHOR = u'A.C.H.U.S.'
DESCRIPTION = u"""
Hay temas que no se pueden tratar a la ligera, temas que requieren sabiduria y conocimiento. Porque no estais preparados. Porque no sabeis de lo que hablais. Porque opinais por opinar, en definitiva
¡Por que no teneis ni puta idea!
es necesario quien aporte Rigor y Criterio."""

IMG = """
<p><img src="{}" /></p>
"""


class PodcastFeed(Rss201rev2Feed):
    def rss_attributes(self):
        return {u"version": self._version, u"xmlns:atom": u"http://www.w3.org/2005/Atom", u'xmlns:itunes': u'http://www.itunes.com/dtds/podcast-1.0.dtd'}

    def add_root_elements(self, handler):
        super(PodcastFeed, self).add_root_elements(handler)
        handler.addQuickElement(u'itunes:subtitle', SUBTITLE)
        handler.addQuickElement(u'itunes:author', AUTHOR)
        handler.addQuickElement(u'itunes:summary', DESCRIPTION)
        handler.addQuickElement(u'itunes:explicit', u'yes')
        handler.addQuickElement(u'itunes:type', u'episodic')
        handler.addQuickElement(u'itunes:category', attrs={u'text': u"TV & Film"})
        handler.addQuickElement(u'itunes:image', attrs={u'href': u"http://rigorycriterio.es/theme/img/social.png"})
        handler.addQuickElement(u'itunes:keywords', "Cine, Television, Comic, Literatura, Videojuegos, Cultura, Pop")

    def add_item(self, title, link, description, **kwargs):
        description += IMG.format(kwargs['thumb'])
        super(PodcastFeed, self).add_item(title, link, description, **kwargs)


    def add_item_elements(self, handler, item):
        super(PodcastFeed, self).add_item_elements(handler, item)
        if item['description']:
            handler.addQuickElement(u'itunes:summary', item['description'])
        handler.addQuickElement(u'itunes:explicit', u'yes')
        handler.addQuickElement(u'itunes:episodeType', u'full')
        handler.addQuickElement(u'itunes:image', attrs={u"href": item['thumb']})
        d = "00:00:00"
        if item['duration'] < 60:
            d = u'00:'+ str(item['duration']).zfill(2) + u':00'
        else:
            d = str(item['duration']/60).zfill(2) + u':00:00'
        handler.addQuickElement(u'itunes:duration', d)



def create_feed(settings):
    return PodcastFeed(title=TITLE,
                          link=settings['SITEURL'],
                          description=settings['SITEDESCRIPTION'],
                          language=settings['DEFAULT_LANG'])


def write_feed(settings, feed):
    spath = os.path.join("output", settings['CATEGORY_FEED_RSS'] % "audio")
    with open(spath, "w") as fp:
        feed.write(fp, 'utf-8')
