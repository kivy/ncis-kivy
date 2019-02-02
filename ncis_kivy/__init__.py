from ncis import route, api_response, request, ncis_weakrefs
from flask import Response, abort
from time import sleep
import kivy
import io


__version__ = '0.1'
__author__ = 'Gabriel Pettier <gabriel@kivy.org>'


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

    return api_response(w.properties())


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

    window = App.get_running_app().root_window
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