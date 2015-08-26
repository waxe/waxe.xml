import os
import tempfile
import json
from pyramid import testing
import pyramid.httpexceptions as exc
from mock import patch
from urllib2 import HTTPError
from lxml import etree
import xmltool
from waxe.core.tests.testing import WaxeTestCase, login_user, LoggedBobTestCase, SETTINGS

from waxe.xml.views.editor import (
    EditorView,
    _get_tags,
    is_valid_filecontent,
    get_xmltool_transform
)


def fake_renderer_func(login):
    return None


def fake_renderer_func_ckeditor(login):
    return xmltool.render.CKeditorRender()


def fake_get_xmltool_transform():
    return 'Hello world'


class TestEditorView(LoggedBobTestCase):
    BOB_RELPATH = 'waxe/xml/tests/files'

    def setUp(self):
        super(TestEditorView, self).setUp()
        self.config.include('waxe.xml.views.editor',
                            route_prefix='/account/{login}')

    def test_is_valid_filecontent(self):
        request = testing.DummyRequest()
        request.xmltool_transform = lambda s: 'Hello ' + s
        view = EditorView(request)
        try:
            is_valid_filecontent(view, 'file.xml', 'plop')
        except exc.HTTPInternalServerError, e:
            self.assertTrue('Start tag' in str(e))

        res = is_valid_filecontent(view, 'file.txt', 'plop')
        self.assertEqual(res, 'plop')

        def func(filecontent):
            return None

        with patch('xmltool.load_string') as m:
            m.side_effect = func
            res = is_valid_filecontent(view, 'file.xml', 'plop')
            self.assertEqual(res, (view, 'file.xml', 'Hello plop'))

    def test_get_xmltool_transform(self):
        request = testing.DummyRequest()
        func = get_xmltool_transform(request)
        self.assertEqual(func, None)

        func_str = '%s.fake_get_xmltool_transform' % (
            fake_get_xmltool_transform.__module__)
        request.registry.settings['waxe.xml.xmltool.transform'] = func_str
        func = get_xmltool_transform(request)
        res = func()
        self.assertEqual(res, 'Hello world')

    def test__get_html_renderer(self):
        request = testing.DummyRequest()
        res = EditorView(request)._get_html_renderer()
        self.assertTrue(isinstance(res, xmltool.render.ContenteditableRender))
        settings = request.registry.settings
        func_str = '%s.fake_renderer_func_ckeditor' % (
            fake_renderer_func_ckeditor.__module__)
        settings['waxe.xml.xmltool.renderer_func'] = func_str
        res = EditorView(request)._get_html_renderer()
        self.assertTrue(isinstance(res, xmltool.render.CKeditorRender))

    def test__get_tags(self):
        path = os.path.join(os.getcwd(), 'waxe/xml/tests/files')
        dtd_url = os.path.join(path, 'exercise.dtd')
        res = _get_tags(dtd_url)
        expected = ['Exercise', 'comments', 'mqm', 'qcm', 'test']
        self.assertEqual(res, expected)

        res = _get_tags(dtd_url, text=True)
        expected = ['choice', 'comment', 'number', 'question']
        self.assertEqual(res, expected)

    def test_edit(self):
        class C(object): pass
        path = os.path.join(os.getcwd(), 'waxe/xml/tests/files')
        self.user_bob.config.root_path = path
        request = testing.DummyRequest()
        request.matched_route = C()
        request.matched_route.name = 'route'
        try:
            EditorView(request).edit()
            assert(False)
        except exc.HTTPClientError, e:
            expected = 'No filename given'
            self.assertEqual(str(e), expected)

        with patch('xmltool.generate_form', return_value='My form content'):
            expected_breadcrumb = (
                '<li><a data-href="/filepath" href="/filepath">root</a>'
                '</li>'
                '<li class="active">file1.xml</li>')
            request = testing.DummyRequest(
                params={'path': 'file1.xml'})
            request.custom_route_path = lambda *args, **kw: '/filepath'
            request.matched_route = C()
            request.matched_route.name = 'route_json'
            res = EditorView(request).edit()
            keys = res.keys()
            keys.sort()
            self.assertEqual(keys, ['content', 'jstree_data'])
            self.assertTrue(
                '<form method="POST" '
                'data-action="/filepath" '
                'data-paste-href="/filepath" '
                'data-add-href="/filepath" '
                'data-comment-href="/filepath" '
                'data-copy-href="/filepath" '
                'id="xmltool-form">' in res['content'])
            self.assertTrue('readonly="readonly"' not in res['content'])
            self.assertTrue(isinstance(res['jstree_data'], dict))

        def raise_func(*args, **kw):
            raise Exception('My error')

        with patch('xmltool.load') as m:
            m.side_effect = raise_func
            request = testing.DummyRequest(
                params={'path': 'file1.xml'})
            request.matched_route = C()
            request.matched_route.name = 'route_json'
            try:
                EditorView(request).edit()
                assert(False)
            except exc.HTTPInternalServerError, e:
                expected = 'My error'
                self.assertEqual(str(e), expected)

        def raise_http_func(*args, **kw):
            raise HTTPError('http://url', 404, 'Not found', [], None)

        with patch('xmltool.load') as m:
            m.side_effect = raise_http_func
            request = testing.DummyRequest(
                params={'path': 'file1.xml'})
            request.matched_route = C()
            request.matched_route.name = 'route_json'
            try:
                EditorView(request).edit()
                assert(False)
            except exc.HTTPInternalServerError, e:
                expected = 'The dtd of file1.xml can\'t be loaded.'
                self.assertEqual(str(e), expected)

        def raise_xml_error(*args, **kw):
            raise etree.XMLSyntaxError('Invalid XML', None, None, None)

        with patch('xmltool.load') as m:
            m.side_effect = raise_xml_error
            request = testing.DummyRequest(
                params={'path': 'file1.xml'})
            request.matched_route = C()
            request.matched_route.name = 'route'
            request.custom_route_path = lambda *args, **kw: '/%s/filepath' % args[0]
            try:
                res = EditorView(request).edit()
                assert(False)
            except Exception, e:
                self.assertEqual(str(e), 'Invalid XML')

    def test_get_tags(self):
        request = testing.DummyRequest()
        try:
            EditorView(request).get_tags()
            assert(False)
        except exc.HTTPClientError, e:
            self.assertEqual(str(e), 'No dtd url given')

        path = os.path.join(os.getcwd(), 'waxe/xml/tests/files')
        dtd_url = os.path.join(path, 'exercise.dtd')
        request = testing.DummyRequest(params={'dtd_url': dtd_url})
        res = EditorView(request).get_tags()
        expected = ['Exercise', 'comments', 'mqm', 'qcm', 'test']
        self.assertEqual(res, expected)

    def test_new(self):
        class C(object): pass
        path = os.path.join(os.getcwd(), 'waxe/xml/tests/files')
        dtd_url = os.path.join(path, 'exercise.dtd')
        request = testing.DummyRequest()
        request.custom_route_path = lambda *args, **kw: '/filepath'
        request.matched_route = C()
        request.matched_route.name = 'route_json'
        request.dtd_urls = [dtd_url]
        # Missing parameters
        try:
            res = EditorView(request).new()
            assert(False)
        except Exception, e:
            self.assertEqual(str(e), "Can't create new XML")

        request = testing.DummyRequest(
            params={
                'dtd_url': dtd_url,
                'dtd_tag': 'Exercise'
            })
        request.dtd_urls = [dtd_url]
        request.custom_route_path = lambda *args, **kw: '/filepath'
        request.matched_route = C()
        request.matched_route.name = 'route_json'
        res = EditorView(request).new()
        self.assertEqual(len(res), 2)
        self.assertTrue(
            '<form method="POST" '
            'data-action="/filepath" '
            'data-paste-href="/filepath" '
            'data-add-href="/filepath" '
            'data-comment-href="/filepath" '
            'data-copy-href="/filepath" '
            'id="xmltool-form">' in res['content'])
        self.assertTrue(isinstance(res['jstree_data'], dict))

        request = testing.DummyRequest(
            params={
                'path': 'file1.xml',
            })
        request.custom_route_path = lambda *args, **kw: '/filepath'
        request.matched_route = C()
        request.matched_route.name = 'route'
        res = EditorView(request).new()
        self.assertEqual(len(res), 2)
        self.assertTrue(
            '<form method="POST" '
            'data-action="/filepath" '
            'data-paste-href="/filepath" '
            'data-add-href="/filepath" '
            'data-comment-href="/filepath" '
            'data-copy-href="/filepath" '
            'id="xmltool-form">' in res['content'])
        self.assertTrue(
            '<input type="hidden" name="_xml_filename" '
            'id="_xml_filename" value="" />' in res['content']
        )
        self.assertTrue(isinstance(res['jstree_data'], dict))

    def test_update(self):
        path = os.path.join(os.getcwd(), 'waxe/xml/tests/files')
        self.user_bob.config.root_path = path
        request = testing.DummyRequest(params={})
        try:
            res = EditorView(request).update()
            assert(False)
        except exc.HTTPClientError, e:
            expected = 'No filename given'
            self.assertEqual(str(e), expected)

        request = testing.DummyRequest(params={'_xml_filename': 'test'})
        try:
            EditorView(request).update()
            assert(False)
        except exc.HTTPClientError, e:
            expected = "No filename extension. It should be '.xml'"
            self.assertEqual(str(e), expected)

        request = testing.DummyRequest(params={'_xml_filename': 'test.doc'})
        try:
            EditorView(request).update()
            assert(False)
        except exc.HTTPClientError, e:
            expected = "Bad filename extension '.doc'. It should be '.xml'"
            self.assertEqual(str(e), expected)

        with patch('xmltool.update', return_value=False):
            request = testing.DummyRequest(
                params={'_xml_filename': 'test.xml'})
            request.custom_route_path = lambda *args, **kw: '/filepath'
            request.xmltool_transform = lambda: (lambda s: s)
            res = EditorView(request).update()
            expected = 'File updated'
            self.assertEqual(res, expected)

        def raise_func(*args, **kw):
            raise Exception('My error')

        with patch('xmltool.update') as m:
            m.side_effect = raise_func
            request = testing.DummyRequest(
                params={'_xml_filename': 'test.xml'})
            request.custom_route_path = lambda *args, **kw: '/filepath'
            request.xmltool_transform = lambda: (lambda s: s)
            expected = 'My error'
            try:
                EditorView(request).update()
                assert(False)
            except exc.HTTPInternalServerError, e:
                self.assertEqual(str(e), expected)

    def test_add_element_json(self):
        path = os.path.join(os.getcwd(), 'waxe/xml/tests/files')
        request = testing.DummyRequest(params={})
        expected = {'error_msg': 'Bad parameter'}
        res = EditorView(request).add_element_json()
        self.assertEqual(res, expected)

        dtd_url = os.path.join(path, 'exercise.dtd')
        request = testing.DummyRequest(params={'dtd_url': dtd_url,
                                               'elt_id': 'Exercise'},
                                       xml_plugins=[])
        res = EditorView(request).add_element_json()
        self.assertTrue(res)
        self.assertTrue(isinstance(res, dict))

    def test_copy_json(self):
        class C(object): pass
        request = testing.DummyRequest(params={})
        request.matched_route = C()
        request.matched_route.name = 'route_json'
        expected = {'error_msg': 'Bad parameter'}
        res = EditorView(request).copy_json()
        self.assertEqual(res, expected)

        request = testing.DummyRequest(params={'elt_id': 'my:element'})
        request.matched_route = C()
        request.matched_route.name = 'route_json'
        res = EditorView(request).copy_json()
        expected = {'info_msg': 'Copied'}
        self.assertEqual(res, expected)
        self.assertEqual(len(request.session), 1)
        clipboard = request.session['clipboard']
        self.assertEqual(clipboard['elt_id'], 'my:element')
        self.assertTrue(clipboard['filename'])

    def test_paste_json(self):
        class C(object): pass
        request = testing.DummyRequest(params={})
        request.matched_route = C()
        request.matched_route.name = 'route_json'
        expected = {'error_msg': 'Bad parameter'}
        res = EditorView(request).paste_json()
        self.assertEqual(res, expected)

        path = os.path.join(os.getcwd(), 'waxe/xml/tests/files')
        dtd_url = os.path.join(path, 'exercise.dtd')
        request = testing.DummyRequest(params={'_xml_dtd_url': dtd_url,
                                               'elt_id': 'Exercise'})
        request.matched_route = C()
        request.matched_route.name = 'route_json'

        res = EditorView(request).paste_json()
        expected = {'error_msg': 'Empty clipboard'}
        self.assertEqual(res, expected)

        request = testing.DummyRequest(params={'_xml_dtd_url': dtd_url,
                                               'elt_id': 'Exercise'})
        request.matched_route = C()
        request.matched_route.name = 'route_json'
        data = {
            'number': {'_value': 'Hello world'}
        }
        filename = tempfile.mktemp()
        open(filename, 'w').write(json.dumps(data))
        request.session['clipboard'] = {
            'filename': filename,
            'elt_id': 'Exercise:number'
        }
        res = EditorView(request).paste_json()
        self.assertEqual(len(res), 4)
        self.assertEqual(res['elt_id'], 'Exercise:number')

        request = testing.DummyRequest(params={'_xml_dtd_url': dtd_url,
                                               'elt_id': 'Exercise'})
        request.matched_route = C()
        request.matched_route.name = 'route_json'
        data = {
            'Exercise': {}
        }
        open(filename, 'w').write(json.dumps(data))
        request.session['clipboard'] = {
            'filename': filename,
            'elt_id': 'Exercise'
        }
        res = EditorView(request).paste_json()
        expected = {'error_msg': 'The element can\'t be pasted here'}
        self.assertEqual(res, expected)


class FunctionalTestEditorView(WaxeTestCase):

    def setUp(self):
        self.settings = SETTINGS.copy()
        self.settings['waxe.editors'] = 'waxe.xml.views.editor'
        self.settings['dtd_urls'] = 'waxe/xml/tests/files/exercise.dtd'
        super(FunctionalTestEditorView, self).setUp()

    def test_forbidden(self):

        for url in [
            '/api/1/account/Bob/xml/edit.json',
            '/api/1/account/Bob/xml/get-tags.json',
            '/api/1/account/Bob/xml/new.json',
            '/api/1/account/Bob/xml/update.json',
            '/api/1/account/Bob/xml/add-element.json',
            '/api/1/account/Bob/xml/get-comment-modal.json',
            '/api/1/account/Bob/xml/copy.json',
            '/api/1/account/Bob/xml/paste.json',
        ]:
            self.testapp.get(url, status=401)

    @login_user('Bob')
    def test_edit(self):
        path = os.path.join(os.getcwd(), 'waxe/xml/tests/files')
        self.user_bob.config.root_path = path
        res = self.testapp.get('/api/1/account/Bob/xml/edit.json', status=400)
        self.assertEqual(res.body,  '"No filename given"')

        res = self.testapp.get('/api/1/account/Bob/xml/edit.json',
                               status=200,
                               params={'path': 'file1.xml'})
        dic = json.loads(res.body)
        self.assertEqual(len(dic), 2)
        expected = (
            '<form method="POST" '
            'data-action="/api/1/account/Bob/xml/update.json" '
            'data-paste-href="/api/1/account/Bob/xml/paste.json" '
            'data-add-href="/api/1/account/Bob/xml/add-element.json" '
            'data-comment-href="/api/1/account/Bob/xml/get-comment-modal.json" '
            'data-copy-href="/api/1/account/Bob/xml/copy.json" '
            'id="xmltool-form">')
        self.assertTrue(expected in dic['content'])
        self.assertTrue(isinstance(dic['jstree_data'], dict))

        self.assertEqual(dic['content'].count('<textarea'), 17)
        self.assertEqual(dic['content'].count('contenteditable="true"'), 17)

        settings = self.testapp.app.app.registry.settings
        func_str = '%s.fake_renderer_func' % fake_renderer_func.__module__
        settings['waxe.xml.xmltool.renderer_func'] = func_str

        res = self.testapp.get('/api/1/account/Bob/xml/edit.json',
                               status=200,
                               params={'path': 'file1.xml'})
        dic = json.loads(res.body)
        self.assertEqual(dic['content'].count('<textarea'), 17)
        self.assertEqual(dic['content'].count('contenteditable="true"'), 0)

    @login_user('Bob')
    def test_get_tags(self):
        path = os.path.join(os.getcwd(), 'waxe/xml/tests/files')
        dtd_url = os.path.join(path, 'exercise.dtd')
        self.user_bob.config.root_path = path
        res = self.testapp.get('/api/1/account/Bob/xml/get-tags.json', status=400)
        self.assertEqual(res.body, '"No dtd url given"')

        res = self.testapp.get('/api/1/account/Bob/xml/get-tags.json',
                               status=200,
                               params={'dtd_url': dtd_url})
        expected = ['Exercise', 'comments', 'mqm', 'qcm', 'test']
        self.assertEqual(json.loads(res.body), expected)

        res = self.testapp.get('/api/1/account/Bob/xml/get-tags.json',
                               status=200,
                               params={'dtd_url': dtd_url, 'text': True})
        expected = ['choice', 'comment', 'number', 'question']
        self.assertEqual(json.loads(res.body), expected)

    @login_user('Bob')
    def test_new(self):
        path = os.path.join(os.getcwd(), 'waxe/xml/tests/files')
        self.user_bob.config.root_path = path
        res = self.testapp.get('/api/1/account/Bob/xml/new.json', status=500)
        self.assertTrue(('Content-Type', 'application/json; charset=UTF-8') in
                        res._headerlist)
        content = json.loads(res.body)
        self.assertEqual(content, "Can't create new XML")

        dtd_url = os.path.join(path, 'exercise.dtd')
        dtd_tag = 'Exercise'
        res = self.testapp.get(
            '/api/1/account/Bob/xml/new.json',
            status=200,
            params={'dtd_url': dtd_url,
                    'dtd_tag': dtd_tag})
        dic = json.loads(res.body)
        self.assertEqual(len(dic), 2)
        expected = (
            '<form method="POST" '
            'data-action="/api/1/account/Bob/xml/update.json" '
            'data-paste-href="/api/1/account/Bob/xml/paste.json" '
            'data-add-href="/api/1/account/Bob/xml/add-element.json" '
            'data-comment-href="/api/1/account/Bob/xml/get-comment-modal.json" '
            'data-copy-href="/api/1/account/Bob/xml/copy.json" '
            'id="xmltool-form">')
        self.assertTrue(expected in dic['content'])
        self.assertTrue(isinstance(dic['jstree_data'], dict))

    @login_user('Bob')
    def test_update(self):
        path = os.path.join(os.getcwd(), 'waxe/xml/tests/files')
        self.user_bob.config.root_path = path
        res = self.testapp.post('/api/1/account/Bob/xml/update.json', status=400)
        expected = '"No filename given"'
        self.assertEqual(res.body, expected)

        with patch('xmltool.update', return_value=False):
            res = self.testapp.post('/api/1/account/Bob/xml/update.json',
                                    status=200,
                                    params={'_xml_filename': 'test.xml'})
            self.assertEqual(res.body, '"File updated"')

    @login_user('Bob')
    def test_add_element_json(self):
        path = os.path.join(os.getcwd(), 'waxe/xml/tests/files')
        self.user_bob.config.root_path = path
        res = self.testapp.get('/api/1/account/Bob/xml/add-element.json', status=200)
        self.assertTrue(('Content-Type', 'application/json; charset=UTF-8') in
                        res._headerlist)
        expected = {"error_msg": "Bad parameter"}
        self.assertEqual(json.loads(res.body), expected)

        dtd_url = os.path.join(path, 'exercise.dtd')
        res = self.testapp.get('/api/1/account/Bob/xml/add-element.json', status=200,
                               params={'dtd_url': dtd_url,
                                       'elt_id': 'Exercise'})

        dic = json.loads(res.body)
        self.assertTrue(dic)

    @login_user('Bob')
    def test_get_comment_modal_json(self):
        path = os.path.join(os.getcwd(), 'waxe/xml/tests/files')
        self.user_bob.config.root_path = path
        res = self.testapp.get('/api/1/account/Bob/xml/get-comment-modal.json', status=200)
        self.assertTrue(('Content-Type', 'application/json; charset=UTF-8') in
                        res._headerlist)
        body = json.loads(res.body)
        self.assertEqual(len(body), 1)
        self.assertTrue('<div class="modal ' in body['content'])
