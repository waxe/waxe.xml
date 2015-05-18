import os
import tempfile
import xmltool
from xmltool import dtd_parser, render as xt_render
from lxml import etree
import json
import importlib

from urllib2 import HTTPError, URLError
from pyramid.view import view_config
from pyramid.renderers import render, Response
import pyramid.httpexceptions as exc
from waxe.core import browser, utils, resource, events
from waxe.core.views.base import BaseUserView
import pyramid_logging

log = pyramid_logging.getLogger(__name__)

import waxe.xml

EXTENSIONS = waxe.xml.EXTENSIONS
ROUTE_PREFIX = waxe.xml.ROUTE_PREFIX


def _get_tags(dtd_url):
    dic = xmltool.dtd_parser.parse(dtd_url=dtd_url)
    lis = []
    for k, v in dic.items():
        if issubclass(v, xmltool.elements.TextElement):
            continue
        lis += [k]
    lis.sort()
    return lis


# Basic plugin system
def match(request, str_id, dtd_url):
    for plugin in request.xml_plugins:
        if plugin.match(request, str_id, dtd_url):
            return plugin


def add_element(request, str_id, dtd_url):
    plugin = match(request, str_id, dtd_url)
    if not plugin:
        return None
    return plugin.add_element(request, str_id, dtd_url)
# end Basic plugin system


def is_valid_filecontent(view, path, filecontent):
    if not os.path.splitext(path)[1] == '.xml':
        return filecontent

    try:
        xmltool.load_string(filecontent)
        transform = view.request.xmltool_transform
        if transform:
            return view, path, transform(filecontent)
        return view, path, filecontent
    except Exception, e:
        raise exc.HTTPInternalServerError(str(e))


class EditorView(BaseUserView):

    def _get_html_renderer(self):
        if 'waxe.xml.xmltool.renderer_func' not in self.request.registry.settings:
            return None

        func = self.request.registry.settings['waxe.xml.xmltool.renderer_func']
        mod, func = func.rsplit('.', 1)
        return getattr(importlib.import_module(mod), func)(
            self.current_user.login)

    @view_config(route_name='edit_json')
    def edit(self):
        filename = self.request.GET.get('path')
        if not filename:
            raise exc.HTTPClientError('No filename given')
        root_path = self.root_path
        absfilename = browser.absolute_path(filename, root_path)
        iframe = 'iframe' in self.request.GET
        try:
            obj = xmltool.load(absfilename)
            if iframe:
                obj.root.html_renderer = xt_render.ReadonlyRender()
                html = obj.to_html()
            else:
                obj.root.html_renderer = self._get_html_renderer()
                html = xmltool.generate_form_from_obj(
                    obj,
                    form_filename=filename,
                    form_attrs={
                        'data-add-href': self.request.custom_route_path('add_element_json'),
                        'data-comment-href': self.request.custom_route_path('get_comment_modal_json'),
                        'data-action': self.request.custom_route_path('update_json'),
                        'data-copy-href': self.request.custom_route_path('copy_json'),
                        'data-paste-href': self.request.custom_route_path('paste_json'),
                    }
                )
            jstree_data = obj.to_jstree_dict()
        except (HTTPError, URLError), e:
            log.exception(e, request=self.request)
            raise exc.HTTPInternalServerError(
                "The dtd of %s can't be loaded." % filename)
        except etree.XMLSyntaxError, e:
            log.exception(e, request=self.request)
            return self.edit_text(e)
        except Exception, e:
            log.exception(e, request=self.request)
            raise exc.HTTPInternalServerError(str(e))

        if 'iframe' in self.request.GET:
            # TODO: we should remove this logic when adding a window to edit
            # tag directly
            return Response(
                render('iframe.mak',
                       {
                           'content': html,
                           'jstree_data': json.dumps(jstree_data),
                       },
                       self.request))

        self.add_opened_file(filename)
        return {
            'content': html,
            'jstree_data': jstree_data,
        }

    @view_config(route_name='edit_text_json')
    def edit_text(self, exception=None):
        filename = self.request.GET.get('path')
        if not filename:
            raise exc.HTTPClientError('No filename given')
        root_path = self.root_path
        absfilename = browser.absolute_path(filename, root_path)
        try:
            content = open(absfilename, 'r').read()
            content = content.decode('utf-8')
        except Exception, e:
            log.exception(e, request=self.request)
            raise exc.HTTPInternalServerError(str(e))

        content = utils.escape_entities(content)

        html = u'<form id="xmltool-form" class="no-tree" data-action="%s" method="POST">' % (
            self.request.custom_route_path('update_text_json'),
        )
        html += u'<input type="hidden" id="_xml_filename" name="filename" value="%s" />' % filename
        html += u'<textarea class="codemirror" name="filecontent">%s</textarea>' % content
        html += u'</form>'

        dic = {
            'content': html,
        }
        # TODO: Support to display message in angular or change this logic
        if exception:
            dic['error_msg'] = str(exception)
        return dic

    @view_config(route_name='get_tags_json')
    def get_tags(self):
        dtd_url = self.request.GET.get('dtd_url', None)
        if not dtd_url:
            raise exc.HTTPClientError('No dtd url given')
        return _get_tags(dtd_url)

    @view_config(route_name='new_json')
    def new(self):
        relpath = self.request.GET.get('path')
        dtd_url = self.request.GET.get('dtd_url')
        dtd_tag = self.request.GET.get('dtd_tag')

        obj = None
        if dtd_tag and dtd_url:
            # Create new object from the dtd url and tag
            try:
                dic = dtd_parser.parse(dtd_url=dtd_url)
            except (HTTPError, URLError), e:
                log.exception(e, request=self.request)
                raise exc.HTTPInternalServerError(
                    "The dtd file %s can't be loaded." % dtd_url)
            if dtd_tag not in dic:
                raise exc.HTTPInternalServerError(
                    'Invalid dtd element: %s (%s)' % (dtd_tag, dtd_url))
            obj = dic[dtd_tag]()
            obj.dtd_url = dtd_url
        elif relpath:
            # Create new object from a template
            absfilename = browser.absolute_path(relpath, self.root_path)
            try:
                obj = xmltool.load(absfilename)
            except Exception, e:
                log.exception(e, request=self.request)
                raise exc.HTTPInternalServerError(str(e))

        if obj:
            obj.root.html_renderer = self._get_html_renderer()
            html = xmltool.generate_form_from_obj(
                obj,
                form_attrs={
                    'data-add-href': self.request.custom_route_path('add_element_json'),
                    'data-comment-href': self.request.custom_route_path('get_comment_modal_json'),
                    'data-action': self.request.custom_route_path('update_json'),
                    'data-copy-href': self.request.custom_route_path('copy_json'),
                    'data-paste-href': self.request.custom_route_path('paste_json'),
                }
            )
            jstree_data = obj.to_jstree_dict()
            return {
                'content': html,
                'jstree_data': jstree_data,
            }

        content = render('blocks/new.mak',
                         {'dtd_urls': self.request.dtd_urls,
                          'tags': _get_tags(self.request.dtd_urls[0])},
                         self.request)
        return {'modal': content}

    @view_config(route_name='update_json')
    def update(self):
        data = self.req_post
        filename = data.pop('_xml_filename', None)
        if not filename:
            raise exc.HTTPClientError('No filename given')

        root, ext = os.path.splitext(filename)
        if ext != '.xml':
            error_msg = 'No filename extension.'
            if ext:
                error_msg = "Bad filename extension '%s'." % ext
            error_msg += " It should be '.xml'"
            raise exc.HTTPClientError(error_msg)

        root_path = self.root_path
        absfilename = browser.absolute_path(filename, root_path)
        try:
            xmltool.update(absfilename, data,
                           transform=self.request.xmltool_transform)
        except (HTTPError, URLError), e:
            log.exception(e, request=self.request)
            raise exc.HTTPInternalServerError(
                "The dtd of %s can't be loaded." % filename)
        except Exception, e:
            log.exception(e, request=self.request)
            raise exc.HTTPInternalServerError(str(e))

        events.trigger('updated.xml',
                       view=self,
                       path=filename)
        return 'File updated'

    @view_config(route_name='update_text_json')
    def update_text(self):
        filecontent = self.req_post.get('filecontent')
        filename = self.req_post.get('filename') or ''
        if not filecontent or not filename:
            raise exc.HTTPClientError('Missing parameters!')
        root_path = self.root_path
        absfilename = browser.absolute_path(filename, root_path)
        try:
            obj = xmltool.load_string(filecontent)
            obj.write(absfilename, transform=self.request.xmltool_transform())
        except Exception, e:
            raise exc.HTTPInternalServerError(str(e))

        # TODO: the modal logic should be in angular
        modal = None
        msg = 'File updated'
        if self.request.POST.get('commit'):
            modal = render('blocks/commit_modal.mak',
                           {}, self.request)

        events.trigger('updated', view=self, paths=filename)
        if modal:
            return {
                'modal': modal
            }

        return msg

    @view_config(route_name='add_element_json')
    def add_element_json(self):
        elt_id = self.request.GET.get('elt_id')
        dtd_url = self.request.GET.get('dtd_url')
        if not elt_id or not dtd_url:
            return {'error_msg': 'Bad parameter'}

        res = add_element(self.request, elt_id, dtd_url)
        if res:
            return res

        dic = xmltool.factory.get_data_from_str_id_for_html_display(
            elt_id,
            dtd_url=dtd_url,
            html_renderer=self._get_html_renderer()
        )
        return dic

    @view_config(route_name='copy_json')
    def copy_json(self):
        if 'elt_id' not in self.request.POST:
            return {'error_msg': 'Bad parameter'}
        data = xmltool.factory.getElementData(self.request.POST['elt_id'],
                                              self.request.POST)
        # Write the content to paste in a temporary file
        filename = tempfile.mktemp()
        open(filename, 'w').write(json.dumps(data))
        self.request.session['clipboard'] = {
            'filename': filename,
            'elt_id': self.request.POST['elt_id'],
        }
        return {'info_msg': 'Copied'}

    @view_config(route_name='paste_json')
    def paste_json(self):
        # TODO: Validate it's the same dtd
        elt_id = self.request.POST.pop('elt_id', None)
        dtd_url = self.request.POST.pop('_xml_dtd_url', None)
        data = xmltool.utils.unflatten_params(self.request.POST)

        if not elt_id or not dtd_url:
            return {'error_msg': 'Bad parameter'}

        clipboard = self.request.session.get('clipboard')
        if not clipboard:
            return {
                'error_msg': 'Empty clipboard'
            }
        filename = clipboard['filename']
        clipboard_data = json.loads(open(filename, 'r').read())

        dic = xmltool.factory.get_new_element_data_for_html_display(
            elt_id, data,
            clipboard_data, dtd_url,
            # Don't keep the attributes nor the comments
            skip_extra=True,
            html_renderer=self._get_html_renderer()
        )
        if not dic:
            return {
                'error_msg': 'The element can\'t be pasted here'
            }

        return dic

    @view_config(route_name='get_comment_modal_json')
    def get_comment_modal_json(self):
        # TODO: remove this function, it should be done in angular
        comment = self.request.GET.get('comment') or ''
        content = render('blocks/comment_modal.mak',
                         {'comment': comment}, self.request)
        return {'content': content}


def get_dtd_urls(request):
    if 'dtd_urls' not in request.registry.settings:
        raise AttributeError('No dtd_urls defined in the ini file.')
    return filter(bool, request.registry.settings['dtd_urls'].split('\n'))


def get_xml_plugins(request):
    if 'waxe.xml.plugins' not in request.registry.settings:
        return []
    lis = filter(bool,
                 request.registry.settings['waxe.xml.plugins'].split('\n'))

    mods = []
    for s in lis:
        mods.append(importlib.import_module(s))
    return mods


def get_xmltool_transform(request):
    """Before writing XML, we can call a function to transform it.
    """
    if 'waxe.xml.xmltool.transform' not in request.registry.settings:
        return None
    func = request.registry.settings['waxe.xml.xmltool.transform']
    mod, func = func.rsplit('.', 1)
    return getattr(importlib.import_module(mod), func)


def includeme(config):
    settings = config.registry.settings
    cache_timeout = settings.get('xmltool.cache_timeout')
    if cache_timeout:
        xmltool.cache.CACHE_TIMEOUT = cache_timeout

    config.set_request_property(get_dtd_urls, 'dtd_urls', reify=True)
    config.set_request_property(get_xml_plugins, 'xml_plugins', reify=True)
    config.set_request_property(get_xmltool_transform, 'xmltool_transform',
                                reify=True)

    config.add_route('edit_json', '/edit.json')
    config.add_route('edit_text_json', '/edit-text.json')
    config.add_route('new_json', '/new.json')
    config.add_route('update_json', '/update.json')
    config.add_route('update_text_json', '/update-text.json')
    config.add_route('add_element_json', '/add-element.json')
    config.add_route('get_comment_modal_json', '/get-comment-modal.json')
    config.add_route('copy_json', '/copy.json')
    config.add_route('paste_json', '/paste.json')
    config.add_route('get_tags_json', '/get-tags.json')
    config.scan(__name__)

    # We have to be sure we don't have any prefix
    config.route_prefix = None
    config.add_static_view(
        'static-xml',
        'waxe.xml:static',
        cache_max_age=3600,
    )

    resource.add_js_resource('waxe.xml:static/jstree.min.js')
    resource.add_js_resource('waxe.xml:static/xmltool.js')
    resource.add_css_resource('waxe.xml:static/xmltool.min.css')
    resource.add_css_resource('waxe.xml:static/themes/default/style.min.css')

    # When we update a file as txt, we validate it if it's an XML.
    events.on('before_update.txt', is_valid_filecontent)
