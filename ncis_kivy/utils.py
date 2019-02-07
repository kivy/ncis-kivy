from threading import Event

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
        ev = Event()
        ev_value = Event()

        def custom_call(dt):
            if f(*args, **kwargs):
                ev_value.set()
            ev.set()

        from kivy.clock import Clock
        Clock.schedule_once(custom_call, 0)
        ev.wait()
        return ev_value.is_set()

    return f2
