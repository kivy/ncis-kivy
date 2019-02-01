from ncis import route, api_response, request, ncis_weakrefs
import kivy

__version__ = '0.1'
__author__ = 'Gabriel Pettier <gabriel@kivy.org>'


@route('/version')
def version():
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


@route('/inspect/<wid>', method='GET')
def inspect(wid):
    wid = int(wid)
    w = ncis_weakrefs.get(wid)

    if w is None:
        return api_response(None)
    w = w()
    if w is None:
        return api_response(None)

    return api_response(w.properties())
