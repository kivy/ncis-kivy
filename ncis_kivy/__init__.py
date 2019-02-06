from ncis import route, api_response, request, ncis_weakrefs, api_error
from ncis_kivy.xpath import XpathParser
from flask import Response, abort
from time import sleep
from itertools import count
import traceback
import threading
import kivy
import io
import re

__version__ = '0.1'
__author__ = 'Gabriel Pettier <gabriel@kivy.org>'

app = None


def kivyapp():
    global app
    if app:
        return app
    from kivy.app import App
    app = App.get_running_app()
    return app


def kivythread(f):
    def f2(*args, **kwargs):
        ev = threading.Event()
        ev_value = threading.Event()

        def custom_call(dt):
            if f(*args, **kwargs):
                ev_value.set()
            ev.set()

        from kivy.clock import Clock
        Clock.schedule_once(custom_call, 0)
        ev.wait()
        return ev_value.is_set()

    return f2


@route('/version')
def kivy_version():
    return api_response({
        'version': kivy.__version__,
    })


@route('/tree')
def tree():
    from kivy.core.window import Window
    return api_response({
        'tree': ('root', _tree(Window))
    })


def _tree(root):
    res = []
    for w in root.children:
        res.append((w, _tree(w)))
    return res


@route('/inspect/<wid>')
def inspect(wid):
    wid = int(wid)
    w = ncis_weakrefs.get(wid)

    if w is None:
        return api_response(None)
    w = w()
    if w is None:
        return api_response(None)

    props = {
        key: {'value': getattr(w, key)}
        for key in w.properties()
    }

    return api_response(props)


screenstream_ctx = {
    "installed": False,
    "data": None,
    "window": None
}

def screenstream_get_loader(fmt):
    from kivy.core.image import ImageLoader
    loaders = [x for x in ImageLoader.loaders if x.can_save(
        fmt, is_bytesio=True)]
    if not loaders:
        return abort(500)
    return loaders[0]


def screenstream_install(fmt):
    if fmt not in ('png', 'jpg'):
        return

    if screenstream_ctx["installed"]:
        return

    from kivy.app import App

    window = kivyapp().root_window
    if not window:
        return

    def _window_flip_and_save(*largs):
        from kivy.graphics.opengl import glReadPixels, GL_RGB, GL_UNSIGNED_BYTE
        width, height = window.size
        pixels = glReadPixels(0, 0, width, height, GL_RGB, GL_UNSIGNED_BYTE)
        screenstream_ctx["data"] = (width, height, "rgb", pixels)

    window.bind(on_flip=_window_flip_and_save)
    screenstream_ctx["installed"] = True
    screenstream_ctx["window"] = window

    return True


def screenstream_get_image(fmt, loader):
    width, height, pixelfmt, pixels = screenstream_ctx["data"]
    bio = io.BytesIO()
    loader.save(bio, width, height, pixelfmt, pixels, True, fmt)
    return bio.read()


@route("/screenshot/<fmt>")
def kivy_screenshot(fmt):
    if not screenstream_install(fmt):
        return abort(500)

    loader = screenstream_get_loader(fmt)
    if not loader:
        return abort(500)

    last_data = screenstream_ctx["data"]
    screenstream_ctx["window"].canvas.ask_update()

    # wait the image to change
    while True:
        # busy sleep if there is no update
        data = screenstream_ctx["data"]
        if data != last_data:
            break
        sleep(0.016)

    data = screenstream_get_image(fmt, loader)
    if not data:
        return abort(500)

    if fmt == 'png':
        mimetype = 'image/png'
    elif fmt == 'jpg':
        mimetype = 'image/jpeg'
    return Response(data, mimetype=mimetype)


@route('/screenstream/<fmt>')
def kivy_screenstream(fmt):
    boundary = "--ncis-screenstream"

    if not screenstream_install(fmt):
        return abort(500)

    window = screenstream_ctx["window"]
    loader = screenstream_get_loader(fmt)
    if not loader:
        return abort(500)

    def _stream():
        last_data = None
        window.canvas.ask_update()
        while True:

            # busy sleep if there is no update
            data = screenstream_ctx["data"]
            if data == last_data:
                yield ''
                sleep(0.016)
                continue
            last_data = data

            image = screenstream_get_image(fmt, loader)
            if not image:
                continue

            # convert and send
            yield '--{}\r\n'.format(boundary)
            if fmt == 'jpg':
                yield 'Content-Type: image/jpeg\r\n'
            elif fmt == 'png':
                yield 'Content-Type: image/png\r\n'
            yield 'Content-Length: %d\r\n\r\n' % len(image)
            yield image


    return Response(_stream(), headers={
        'Content-type': 'multipart/x-mixed-replace; boundary={}'.format(
            boundary
        )
    })

#
# Pick & actions
# most implementation came from telenium
#

telenium_input = False
NCISMotionEvent = None
NCISInputProvider = None
_next_id = count()

def _register_input_provider():
    global telenium_input, NCISMotionEvent, NCISINputProvider
    if telenium_input:
        return

    from kivy.input.motionevent import MotionEvent
    from kivy.input.provider import MotionEventProvider

    class NCISMotionEvent(MotionEvent):
        def depack(self, args):
            self.is_touch = True
            self.sx, self.sy = args[:2]
            super(NCISMotionEvent, self).depack(args)


    class NCISInputProvider(MotionEventProvider):
        events = []

        def update(self, dispatch_fn):
            while self.events:
                event = self.events.pop(0)
                dispatch_fn(*event)

    telenium_input = NCISInputProvider('ncis', None)
    from kivy.base import EventLoop
    EventLoop.add_input_provider(telenium_input)


def _path_to(widget):
    from kivy.core.window import Window
    root = Window
    if widget.parent is root or widget.parent == widget or not widget.parent:
        return "/{}".format(widget.__class__.__name__)
    return "{}/{}[{}]".format(
        _path_to(widget.parent), widget.__class__.__name__,
        widget.parent.children.index(widget))

def _select_all(selector, root=None):
    app = kivyapp()
    if not app:
        return []
    if root is None:
        root = app.root.parent
    parser = XpathParser()
    matches = parser.parse(selector)
    matches = matches.execute(root)
    return matches or []


def _select_first(selector, root=None):
    matches = _select_all(selector, root=root)
    if matches:
        return matches[0]


def _pick_widget(widget, x, y):
    ret = None
    # try to filter widgets that are not visible (invalid inspect target)
    if (hasattr(widget, 'visible') and not widget.visible):
        return ret
    if widget.collide_point(x, y):
        ret = widget
        x2, y2 = widget.to_local(x, y)
        # reverse the loop - look at children on top first
        for child in reversed(widget.children):
            ret = _pick_widget(child, x2, y2) or ret
    return ret


def _collide_at(widget, x, y):
    if widget.collide_point(x, y):
        x2, y2 = widget.to_local(x, y)
        have_results = False
        for child in reversed(widget.children):
            for ret in _collide_at(child, x2, y2):
                yield ret
                have_results = True
        if not have_results:
            yield widget


@kivythread
def _send_keycode(key, scancode, sym, modifiers):
    from kivy.core.window import Window
    print("Telenium: send key key={!r} scancode={} sym={!r} modifiers={}".format(
        key, scancode, sym, modifiers
    ))
    if not Window.dispatch("on_key_down", key, scancode, sym, modifiers):
        Window.dispatch("on_keyboard", key, scancode, sym, modifiers)
    Window.dispatch("on_key_up", key, scancode)
    return True


@route('/exists', methods=['POST'])
def rpc_exists():
    selector = request.form.get('selector')
    if not selector:
        return api_error('Missing `selector`')
    result = _select_first(selector)
    return api_response({'result': result is not None})


@route('/select', methods=['POST'])
def rpc_select():
    selector = request.form.get('selector')
    if not selector:
        return api_error('Missing `selector`')
    with_bounds = bool(request.form.get('with_bounds'))
    if not with_bounds:
        results = list(map(_path_to, _select_all(selector)))
        return api_response({
            'selector': selector,
            'with_bounds': with_bounds,
            'results': results
        })

    results = []
    for widget in _select_all(selector):
        left, bottom = widget.to_window(widget.x, widget.y)
        right, top = widget.to_window(widget.x + widget.width, widget.y + widget.height)
        bounds = (left, bottom, right, top)
        path = _path_to(widget)
        results.append((path, bounds))

    return api_response({
        'selector': selector,
        'with_bounds': with_bounds,
        'results': results
    })


@route('/setattr', methods=['POST'])
def rpc_setattr():
    selector = request.form.get('selector')
    if not selector:
        return api_error('Missing `selector`')
    key = request.form.get('key')
    if not key:
        return api_error('Missing `key`')
    value = request.form.get('value')
    if not value:
        return api_error('Missing `value`')

    updated = 0
    for widget in _select_all(selector):
        setattr(widget, key, value)
        updated += 1

    return api_response({
        'updated': updated
    })


@route('/click', methods=['POST'])
def rpc_click():
    global _next_id
    selector = request.form.get('selector')
    if not selector:
        return api_error('Missing `selector`')
    w = _select_first(selector)
    if not w:
        return api_error('No widget matching `selector`')

    _register_input_provider()
    from kivy.core.window import Window
    cx, cy = w.to_window(w.center_x, w.center_y)
    sx = cx / float(Window.width)
    sy = cy / float(Window.height)
    me = NCISMotionEvent(
        "ncis_me", id=next(_next_id), args=[sx, sy])
    telenium_input.events.append(("begin", me))
    telenium_input.events.append(("end", me))
    return api_response()


@route('/pick')
def rpc_pick(all=False):
    from kivy.core.window import Window
    widgets = []
    ev = threading.Event()

    def on_touch_down(touch):
        root = kivyapp().root
        for widget in Window.children:
            if all:
                widgets.extend(list(_collide_at(root, touch.x, touch.y)))
            else:
                widget = _pick_widget(root, touch.x, touch.y)
                widgets.append(widget)
        ev.set()
        return True

    orig_on_touch_down = Window.on_touch_down
    Window.on_touch_down = on_touch_down
    ev.wait()
    Window.on_touch_down = orig_on_touch_down
    ret = []
    if widgets:
        if all:
            ret = list(map(_path_to, widgets))
        else:
            ret = _path_to(widgets[0])
    return api_response({'results': ret})


@route('/sendkeycodes', methods=['POST'])
def rpc_send_keycode():
    keycodes = request.form.get('keycodes')
    if not keycodes:
        return api_error('Missing `keycodes`')

    # very hard to get it right, not fully tested and fail proof.
    # just the basics.
    from kivy.core.window import Keyboard
    keys = keycodes.split("+")
    scancode = 0
    key = None
    sym = ""
    modifiers = []
    for el in keys:
        if re.match("^[A-Z]", el):
            lower_el = el.lower()
            # modifier detected ? add it
            if lower_el in ("ctrl", "meta", "alt", "shift"):
                modifiers.append(lower_el)
                continue
            # not a modifier, convert to scancode
            sym = lower_el
            key = Keyboard.keycodes.get(lower_el, 0)
        else:
            # may fail, so nothing would be done.
            try:
                key = int(el)
                sym = unichr(key)
            except Exception as e:
                traceback.print_exc()
                return api_error(e)
    _send_keycode(key, scancode, sym, modifiers)
    return api_response()
