from twisted.trial import unittest
from twisted.internet import threads
import deluge.component as component

class testcomponent(component.Component):
    def __init__(self, name):
        component.Component.__init__(self, name)
        self.start_count = 0
        self.stop_count = 0

    def start(self):
        self.start_count += 1

    def stop(self):
        self.stop_count += 1

class testcomponent_delaystart(testcomponent):
    def start(self):
        def do_sleep():
            import time
            time.sleep(1)
        d = threads.deferToThread(do_sleep)
        def on_done(result):
            self.start_count += 1
        return d.addCallback(on_done)

class testcomponent_update(component.Component):
    def __init__(self, name):
        component.Component.__init__(self, name)
        self.counter = 0
        self.start_count = 0
        self.stop_count = 0

    def update(self):
        self.counter += 1

    def stop(self):
        self.stop_count += 1

class testcomponent_shutdown(component.Component):
    def __init__(self, name):
        component.Component.__init__(self, name)
        self.shutdowned = False
        self.stop_count = 0

    def shutdown(self):
        self.shutdowned = True

    def stop(self):
        self.stop_count += 1

class ComponentTestClass(unittest.TestCase):
    def tearDown(self):
        component._ComponentRegistry.components = {}

    def test_start_component(self):
        def on_start(result, c):
            self.assertEquals(c._component_state, "Started")
            self.assertEquals(c.start_count, 1)

        c = testcomponent("test_start_c1")
        d = component.start(["test_start_c1"])
        d.addCallback(on_start, c)
        return d

    def test_start_depends(self):
        def on_start(result, c1, c2):
            self.assertEquals(c1._component_state, "Started")
            self.assertEquals(c2._component_state, "Started")
            self.assertEquals(c1.start_count, 1)
            self.assertEquals(c2.start_count, 1)

        c1 = testcomponent("test_start_depends_c1")
        c2 = testcomponent("test_start_depends_c2")
        c2._component_depend = ["test_start_depends_c1"]

        d = component.start(["test_start_depends_c2"])
        d.addCallback(on_start, c1, c2)
        return d

    def start_with_depends(self):
        c1 = testcomponent_delaystart("test_start_all_c1")
        c2 = testcomponent("test_start_all_c2")
        c3 = testcomponent_delaystart("test_start_all_c3")
        c4 = testcomponent("test_start_all_c4")
        c5 = testcomponent("test_start_all_c5")

        c3._component_depend = ["test_start_all_c5", "test_start_all_c1"]
        c4._component_depend = ["test_start_all_c3"]
        c2._component_depend = ["test_start_all_c4"]

        d = component.start()
        return (d, c1, c2, c3, c4, c5)

    def finish_start_with_depends(self, *args):
        for c in args[1:]:
            component.deregister(c)

    def test_start_all(self):
        def on_start(*args):
            for c in args[1:]:
                self.assertEquals(c._component_state, "Started")
                self.assertEquals(c.start_count, 1)

        ret = self.start_with_depends()
        ret[0].addCallback(on_start, *ret[1:])
        ret[0].addCallback(self.finish_start_with_depends, *ret[1:])
        return ret[0]

    def test_register_exception(self):
        c1 = testcomponent("test_register_exception_c1")
        self.assertRaises(
            component.ComponentAlreadyRegistered,
            testcomponent,
            "test_register_exception_c1")

    def test_stop_component(self):
        def on_stop(result, c):
            self.assertEquals(c._component_state, "Stopped")
            self.assertFalse(c._component_timer.running)
            self.assertEquals(c.stop_count, 1)

        def on_start(result, c):
            self.assertEquals(c._component_state, "Started")
            return component.stop(["test_stop_component_c1"]).addCallback(on_stop, c)

        c = testcomponent_update("test_stop_component_c1")
        d = component.start(["test_stop_component_c1"])
        d.addCallback(on_start, c)
        return d

    def test_stop_all(self):
        def on_stop(*args):
            for c in args[1:]:
                self.assertEquals(c._component_state, "Stopped")
                self.assertEquals(c.stop_count, 1)

        def on_start(*args):
            for c in args[1:]:
                self.assertEquals(c._component_state, "Started")
            return component.stop().addCallback(on_stop, *args[1:])

        ret = self.start_with_depends()
        ret[0].addCallback(on_start, *ret[1:])
        ret[0].addCallback(self.finish_start_with_depends, *ret[1:])
        return ret[0]

    def test_update(self):
        def on_start(result, c1, counter):
            self.assertTrue(c1._component_timer)
            self.assertTrue(c1._component_timer.running)
            self.assertNotEqual(c1.counter, counter)
            return component.stop()

        c1 = testcomponent_update("test_update_c1")
        cnt = int(c1.counter)
        d = component.start(["test_update_c1"])

        d.addCallback(on_start, c1, cnt)
        return d

    def test_pause(self):
        def on_pause(result, c1, counter):
            self.assertEqual(c1._component_state, "Paused")
            self.assertNotEqual(c1.counter, counter)
            self.assertFalse(c1._component_timer.running)

        def on_start(result, c1, counter):
            self.assertTrue(c1._component_timer)
            self.assertNotEqual(c1.counter, counter)
            d = component.pause(["test_pause_c1"])
            d.addCallback(on_pause, c1, counter)
            return d

        c1 = testcomponent_update("test_pause_c1")
        cnt = int(c1.counter)
        d = component.start(["test_pause_c1"])

        d.addCallback(on_start, c1, cnt)
        return d

    def test_shutdown(self):
        def on_shutdown(result, c1):
            self.assertTrue(c1.shutdowned)
            self.assertEquals(c1._component_state, "Stopped")
            self.assertEquals(c1.stop_count, 1)

        def on_start(result, c1):
            d = component.shutdown()
            d.addCallback(on_shutdown, c1)
            return d

        c1 = testcomponent_shutdown("test_shutdown_c1")
        d = component.start(["test_shutdown_c1"])
        d.addCallback(on_start, c1)
        return d
