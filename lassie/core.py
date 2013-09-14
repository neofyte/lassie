# -*- coding: utf-8 -*-

"""
lassie.core
~~~~~~~~~~~

This module contains a Lassie object to maintain settings across lassie.

"""

from bs4 import BeautifulSoup
import requests

from .compat import urljoin
from .exceptions import LassieError
from .filters import FILTER_MAPS
from .utils import clean_text, convert_to_int

def merge_settings(fetch_setting, class_setting):
    """Merge settings for ``fetch``, method params have priority."""
    if fetch_setting is None:
        return class_setting

    if class_setting is None:
        return fetch_setting

    return fetch_setting


class Lassie(object):
    __attrs__ = [
        'open_graph', 'twitter_card', 'touch_icon', 'favicon',
        'all_images', 'parser'
    ]

    def __init__(self):
        """Instantiates an instance of Lassie."""
        self.open_graph = None
        self.twitter_card = None
        self.touch_icon = None
        self.favicon = None
        self.all_images = None
        self.parser = 'html5lib'

    def __repr__(self):
        return '<Lassie [parser: %s]>' % (self.parser)

    def fetch(self, url, open_graph=True, twitter_card=True, touch_icon=True,
              favicon=True, all_images=False, parser=None):
        """Retrieves content from the specified url, parses it, and returns
        a beautifully crafted dictionary of important information about that
        web page.

        Priority tree is as follows:
            1. Open Graph
            2. Twitter Card
            3. Other meta content (i.e. description, keywords)

        :param url: URL to send a GET request to
        :param open_graph: (optional) If ``True``, filters web page content for Open Graph meta tags. The content of these properties have top priority on return values.
        :type open_graph: bool
        :param twitter_card: (optional) If ``True``, filters web page content for Twitter Card meta tags
        :type twitter_card: bool
        :param touch_icon: (optional) If ``True``, retrieves Apple touch icons and includes them in the response ``images`` array
        :type touch_icon: bool
        :param favicon: (optional) If ``True``, retrieves any favicon images and includes them in the response ``images`` array
        :type favicon: bool
        :param all_images: (optional) If ``True``, retrieves images inside web pages body and includes them in the response ``images`` array. Default: False
        :type all_images: bool
        :param parser: (optional) String reference for the parser that BeautifulSoup will use
        :type parser: string

        """

        # Set params, method params have priority over class params
        open_graph = merge_settings(open_graph, self.open_graph)
        twitter_card = merge_settings(twitter_card, self.twitter_card)
        touch_icon = merge_settings(touch_icon, self.touch_icon)
        favicon = merge_settings(favicon, self.favicon)
        all_images = merge_settings(all_images, self.all_images)
        parser = merge_settings(parser or self.parser, self.parser)

        html = self._retreive_content(url)
        if not html:
            raise LassieError('There was no content to parse.')

        soup = BeautifulSoup(clean_text(html), parser)

        data = {
            'images': [],
            'videos': [],
        }

        if open_graph:
            data.update(self._filter_meta_data('open_graph', soup, data, url))

        if twitter_card:
            data.update(self._filter_meta_data('twitter_card', soup, data, url))

        data.update(self._filter_meta_data('generic', soup, data, url))

        if touch_icon:
            data.update(self._filter_link_tag_data('touch_icon', soup, data, url))

        if favicon:
            data.update(self._filter_link_tag_data('favicon', soup, data, url))

        if all_images:
            # Maybe filter out 1x1, no "good" way to do this if image doesn't supply width/height
            data.update(self._find_all_images(soup, data))

        # TODO: Find a good place for this
        if not 'url' in data:
            data['url'] = url

        if not 'title' in data:
            data['title'] = soup.title.string

        return data

    def _retreive_content(self, url):
        try:
            response = requests.get(url)
        except requests.exceptions.RequestException as e:
            raise LassieError(e)
        else:
            return response.text

    def _filter_meta_data(self, source, soup, data):
        """This method filters the web page content for meta tags that match patterns given in the ``FILTER_MAPS``

        :param source: The key of the meta dictionary in ``FILTER_MAPS['meta']``
        :type source: string
        :param soup: BeautifulSoup instance to find meta tags
        :type soup: instance
        :param data: The response dictionary to manipulate
        :type data: (dict)

        """
        meta = FILTER_MAPS['meta'][source]
        meta_map = meta['map']

        html = soup.find_all('meta', {meta['key']: meta['pattern']})

        image = {}
        video = {}

        for line in html:
            prop = line.get(meta['key'])
            value = line.get('content')

            if prop in meta_map and not meta_map[prop] in data:
                # this could be bad in cases where any values that the property
                # is mapped up to (i.e. "src", "type", etc) are found in ``data``
                # TODO: Figure out a smoother way to prevent conflicts ^^^^^^^^
                image_prop = meta['image_key']
                video_prop = meta['video_key']

                if prop.startswith((image_prop, video_prop)) and \
                prop.endswith(('width', 'height')):
                    if prop.endswith(('width', 'height')):
                        value = convert_to_int(value)

                if prop == 'keywords':
                    value = value.split(',')

                if image_prop and prop.startswith(image_prop) and value:
                    image[meta_map[prop]] = value \
                        if value.startswith(u'http' or u'www') else urljoin(url, value)
                elif video_prop and prop.startswith(video_prop) and value:
                    video[meta_map[prop]] = value
                else:
                    data[meta_map[prop]] = value

        if image:
            image['type'] = image_prop
            data['images'].append(image)
        if video:
            data['videos'].append(video)

        return data

    def _filter_link_tag_data(self, source, soup, data, url):
        """This method filters the web page content for link tags that match patterns given in the ``FILTER_MAPS``

        :param source: The key of the meta dictionary in ``FILTER_MAPS['link']``
        :type source: string
        :param soup: BeautifulSoup instance to find meta tags
        :type soup: instance
        :param data: The response dictionary to manipulate
        :type data: (dict)
        :param url: URL used for making an absolute url
        :type url: string

        """
        link = FILTER_MAPS['link'][source]

        html = soup.find_all('link', {link['key']: link['pattern']})

        for line in html:
            data['images'].append({
                'src': urljoin(url, line.get('href')),
                'type': link['type'],
            })

        return data

    def _find_all_images(self, soup, data):
        """This method finds all images in the web page content

        :param soup: BeautifulSoup instance to find meta tags
        :type soup: instance
        :param data: The response dictionary to manipulate
        :type data: (dict)

        """
        all_images = soup.findAll('img')
        for image in all_images:
            # Create image list then remove duplicate images?
            img = {
                'src': image.get('src'),
                'alt': image.get('alt', ''),
                'type': u'body_image',
            }

            # Only include width and height if included as an attribute of the element
            width = convert_to_int(image.get('width'))
            if width:
                img['width'] = width

            height = convert_to_int(image.get('height'))
            if height:
                image['height'] = height

            data['images'].append(img)

        return data
